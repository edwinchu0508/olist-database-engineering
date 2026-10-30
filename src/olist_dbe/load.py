"""Load pipeline: CSV files -> raw -> DQ checks -> core.

core keeps the same tables for the life of the database (created by `olist-dbe init`). A load stages
the source files in raw, runs the DQ checks, and then publishes in a single transaction: one MERGE
per core table inserts the new keys, updates the rows that changed and deletes the keys that are
gone. MVCC does the rest. Readers are never blocked, and every snapshot sees exactly one complete
version: a snapshot taken before the commit keeps seeing the previous rows after it, including a
REPEATABLE READ transaction that only reads core later, and one taken after sees only the new rows.

Outcomes of run_load():
- it returns a LoadResult: the new version is committed. Failures after the commit (statistics,
  releasing the lock) are listed in LoadResult.cleanup_errors and do not undo anything.
- it raises PublishOutcomeUnknown: the connection broke during the commit and a new connection could
  not establish whether it went through. core holds either the previous or the new version.
- it raises anything else: nothing was published, core is exactly as it was.
"""
import contextlib
import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import psycopg
from psycopg import sql

from . import config, db, dq
from .config import Target

SOURCE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}
CORE_SOURCES_DIR = config.SQL_DIR / "core" / "sources"
MANIFEST_PATH = config.REPO_ROOT / "data_manifest.json"
CHUNK_BYTES = 1 << 20

# Session-level advisory lock that serialises loaders. Any constant works; it only has to be unique
# among the advisory locks used in this database.
LOCK_KEY = 20261029

# The publish waits at most this long for a table lock (e.g. behind a CREATE INDEX of a benchmark run)
# and then fails without having changed anything, instead of queueing every reader behind it.
PUBLISH_LOCK_TIMEOUT = "30s"

# How long a new connection keeps trying to establish the outcome of a commit whose reply was lost.
CONFIRM_TIMEOUT_S = 5.0

# Recording a failed run is best effort: if the database cannot be reached, the next load marks the run
# as abandoned.
_BOOKKEEPING_ERRORS = contextlib.suppress(psycopg.Error, config.ConfigError)

# Test hooks: where run_load() simulates a failure.
#   publish             raise inside the publish transaction, before COMMIT
#   lost_before_commit  the connection dies inside the publish transaction, before COMMIT
#   lost_after_commit   the connection dies right after COMMIT, as when the reply to COMMIT is lost
FAULT_POINTS = ("publish", "lost_before_commit", "lost_after_commit")


class LoadError(Exception):
    """A load stopped before publishing; core is unchanged."""


class LoadInProgress(LoadError):
    pass


class SourceFileError(LoadError):
    pass


class BlockingChecksFailed(LoadError):
    pass


class InjectedFault(LoadError):
    pass


class PublishOutcomeUnknown(Exception):
    """The commit may or may not have happened. Deliberately not a LoadError: core may have changed."""


@dataclass(frozen=True)
class SourceFile:
    table: str
    path: Path
    sha256: str
    size: int
    header: tuple[str, ...]


class Change(NamedTuple):
    inserted: int
    updated: int
    deleted: int


@dataclass(frozen=True)
class LoadResult:
    load_id: int
    changes: dict[str, Change]
    cleanup_errors: tuple[str, ...] = ()
    # True when the connection broke during the commit and a new connection confirmed the publish.
    confirmed_after_disconnect: bool = False


def inspect_files(data_dir: Path) -> list[SourceFile]:
    """Check that every source file exists; hash it and read its header. Touches no database."""
    missing = [name for name in SOURCE_FILES.values() if not (data_dir / name).is_file()]
    if missing:
        raise SourceFileError(f"missing in {data_dir}: {', '.join(missing)}")
    return [_inspect(table, data_dir / name) for table, name in SOURCE_FILES.items()]


def _inspect(table: str, path: Path) -> SourceFile:
    """Hash and header come from one read of the file, so they always describe the same bytes."""
    digest, size, first = hashlib.sha256(), 0, b""
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_BYTES):
            if not size:
                first = chunk
            digest.update(chunk)
            size += len(chunk)
    try:
        # utf-8-sig: the translation file starts with a byte-order mark.
        line = first.split(b"\n", 1)[0].rstrip(b"\r").decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceFileError(f"{path.name}: header is not UTF-8: {exc}") from exc
    return SourceFile(table, path, digest.hexdigest(), size, tuple(next(csv.reader([line]), [])))


def manifest(files: list[SourceFile]) -> dict[str, dict]:
    return {f.path.name: {"sha256": f.sha256, "bytes": f.size} for f in files}


def reference_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceFileError(f"{MANIFEST_PATH.name} is not valid UTF-8 JSON: {exc}") from exc


def run_load(data_dir: Path, *, target: Target, fault: str | None = None) -> LoadResult:
    """Load `data_dir` into core on `target`. See the module docstring for the possible outcomes."""
    if fault is not None and fault not in FAULT_POINTS:
        raise ValueError(f"unknown fault point {fault!r}")
    files = inspect_files(data_dir)

    with db.connect(target) as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
            raise LoadInProgress("another load holds the loader lock")
        try:
            result = _load(conn, target, data_dir, files, fault)
        finally:
            released = _release_lock(conn)
    return LoadResult(result.load_id, result.changes, result.cleanup_errors + released,
                      result.confirmed_after_disconnect)


def _load(conn: psycopg.Connection, target: Target, data_dir: Path, files: list[SourceFile],
          fault: str | None) -> LoadResult:
    # Holding the lock proves no loader is running, so a 'running' row is a crashed load.
    conn.execute(
        "UPDATE meta.load_runs SET status = 'failed', finished_at = clock_timestamp(),"
        " error = 'abandoned: the loader exited without finishing' WHERE status = 'running'"
    )
    load_id = conn.execute(
        "INSERT INTO meta.load_runs (status, data_dir) VALUES ('running', %s) RETURNING load_id",
        (str(data_dir),),
    ).fetchone()[0]

    publishing = False
    try:
        _record_files(conn, load_id, files)
        _check_headers(conn, files)
        _stage(conn, load_id, files)
        results = dq.run_checks(conn, load_id)
        blocked = [r.check.name for r in results if r.check.severity == "blocking" and r.status != "pass"]
        if blocked:
            raise BlockingChecksFailed(f"blocking checks did not pass: {', '.join(blocked)}")
        backend = conn.execute(
            "SELECT pid, backend_start FROM pg_stat_activity WHERE pid = pg_backend_pid()"
        ).fetchone()
        publishing = True
        changes = _publish(conn, load_id, fault)
    except Exception as exc:
        # Only the publish transaction writes core, and with the connection intact psycopg has seen
        # its outcome: an exception means it rolled back.
        if not (publishing and conn.broken):
            _mark_failed(conn, load_id, exc)
            raise
        outcome = confirm_publish(target, load_id, backend)
        if outcome == "unknown":
            raise PublishOutcomeUnknown(
                f"the connection broke during the publish of load {load_id}, and whether it committed could"
                f" not be established within {CONFIRM_TIMEOUT_S:g} s. core holds either the previous or the"
                f" new version: check meta.load_runs (`olist-dbe status`) before relying on it"
            ) from exc
        if outcome == "not_published":
            with _BOOKKEEPING_ERRORS:
                with db.connect(target) as other:
                    _mark_failed(other, load_id, exc)
            raise LoadError(f"the connection broke before the commit; load {load_id} was not published") from exc
        # Published. From here on nothing may raise: a failure would be reported as a failed load.
        changes, cleanup = {}, []
        try:
            with db.connect(target) as other:
                changes = recorded_changes(other, load_id)
                cleanup += _maintain(other)
        except Exception as exc2:
            cleanup.append(f"reconnecting after the commit failed: {type(exc2).__name__}: {exc2}")
        return LoadResult(load_id, changes, tuple(cleanup), confirmed_after_disconnect=True)
    return LoadResult(load_id, changes, tuple(_maintain(conn)))


def _record_files(conn: psycopg.Connection, load_id: int, files: list[SourceFile]) -> None:
    reference = reference_manifest()
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO meta.load_files (load_id, table_name, file_name, sha256, bytes, matches_reference)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (load_id, f.table, f.path.name, f.sha256, f.size,
                 reference[f.path.name]["sha256"] == f.sha256 if f.path.name in reference else None)
                for f in files
            ],
        )


def _columns(conn: psycopg.Connection, relation: str) -> tuple[str, ...]:
    return tuple(
        row[0]
        for row in conn.execute(
            "SELECT attname FROM pg_attribute"
            " WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped ORDER BY attnum",
            (relation,),
        )
    )


def _check_headers(conn: psycopg.Connection, files: list[SourceFile]) -> None:
    """The raw table definitions are the expected header of each file."""
    for f in files:
        expected = _columns(conn, f"raw.{f.table}")
        if f.header != expected:
            raise SourceFileError(f"{f.path.name}: header {list(f.header)} does not match raw.{f.table} {list(expected)}")


def _stage(conn: psycopg.Connection, load_id: int, files: list[SourceFile]) -> None:
    """Replace the contents of raw.* with the source files, all or nothing.

    The bytes sent to COPY are hashed on the way. Unless they are exactly the bytes whose SHA-256 is
    recorded in meta.load_files (and compared with data_manifest.json), nothing is staged.
    """
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE {}").format(sql.SQL(", ").join(sql.Identifier("raw", f.table) for f in files)))
        for f in files:
            copy_stmt = sql.SQL("COPY {} FROM STDIN (FORMAT csv, HEADER true)").format(sql.Identifier("raw", f.table))
            digest, size = hashlib.sha256(), 0
            with cur.copy(copy_stmt) as copy, f.path.open("rb") as fh:
                while chunk := fh.read(CHUNK_BYTES):
                    digest.update(chunk)
                    size += len(chunk)
                    copy.write(chunk)
            if (digest.hexdigest(), size) != (f.sha256, f.size):
                raise SourceFileError(
                    f"{f.path.name} changed while it was being loaded: COPY received {size:,} bytes with"
                    f" SHA-256 {digest.hexdigest()}, but {f.size:,} bytes with {f.sha256} were recorded"
                )
            cur.execute(
                "UPDATE meta.load_files SET rows_loaded = %s WHERE load_id = %s AND table_name = %s",
                (cur.rowcount, load_id, f.table),
            )


def publish_statements(conn: psycopg.Connection) -> list[tuple[str, sql.Composed]]:
    """One MERGE per core table that turns its rows into the new version, in sql/core/sources order.

    The new rows come from sql/core/sources/NN_<table>.sql; columns and the primary key from the
    catalog. Each MERGE inserts the new keys, updates rows whose other columns changed (unchanged rows
    are not rewritten) and deletes the keys that are gone. It returns one row: inserted, updated,
    deleted.
    """
    sources = {path.stem.split("_", 1)[1]: path for path in sorted(CORE_SOURCES_DIR.glob("*.sql"))}
    tables = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'core'")}
    if set(sources) != tables:
        raise LoadError(f"sql/core/sources has queries for {sorted(sources)}, but core has tables {sorted(tables)}")

    statements = []
    for table, path in sources.items():
        query = path.read_text(encoding="utf-8").strip().rstrip(";") + "\n"
        columns = _columns(conn, f"core.{table}")
        produced = tuple(c.name for c in conn.execute(f"SELECT * FROM (\n{query}) AS s LIMIT 0").description)
        if sorted(produced) != sorted(columns):
            raise LoadError(f"{path.name} returns columns {list(produced)}, core.{table} has {list(columns)}")
        key = tuple(
            row[0]
            for row in conn.execute(
                "SELECT a.attname FROM pg_constraint AS c"
                " CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, n)"
                " JOIN pg_attribute AS a ON a.attrelid = c.conrelid AND a.attnum = k.attnum"
                " WHERE c.conrelid = %s::regclass AND c.contype = 'p' ORDER BY k.n",
                (f"core.{table}",),
            )
        )
        statements.append((table, _merge(table, columns, key, query)))
    return statements


def _merge(table: str, columns: tuple[str, ...], key: tuple[str, ...], query: str) -> sql.Composed:
    def cols(alias: str | None, names) -> sql.Composable:
        return sql.SQL(", ").join(sql.Identifier(alias, c) if alias else sql.Identifier(c) for c in names)

    def pairs(names, template: str, separator: str) -> sql.Composable:
        return sql.SQL(separator).join(
            sql.SQL(template).format(sql.Identifier("t", c), sql.Identifier("s", c), sql.Identifier(c)) for c in names
        )

    rest = [c for c in columns if c not in key]
    clauses = []
    if rest:
        clauses.append(sql.SQL("    WHEN MATCHED AND ({}) IS DISTINCT FROM ({}) THEN\n        UPDATE SET {}\n").format(
            cols("t", rest), cols("s", rest), pairs(rest, "{2} = {1}", ", ")))
    clauses.append(sql.SQL(
        "    WHEN NOT MATCHED BY TARGET THEN\n        INSERT ({}) VALUES ({})\n"
        "    WHEN NOT MATCHED BY SOURCE THEN\n        DELETE\n"
    ).format(cols(None, columns), cols("s", columns)))
    return sql.SQL(
        "WITH changes AS (\n"
        "    MERGE INTO {table} AS t\n"
        "    USING (\n{query}    ) AS s\n"
        "    ON {on}\n"
        "{clauses}"
        "    RETURNING merge_action() AS action\n"
        ")\n"
        "SELECT count(*) FILTER (WHERE action = 'INSERT'),\n"
        "       count(*) FILTER (WHERE action = 'UPDATE'),\n"
        "       count(*) FILTER (WHERE action = 'DELETE')\n"
        "FROM changes"
    ).format(table=sql.Identifier("core", table), query=sql.SQL(query), on=pairs(key, "{0} = {1}", " AND "),
             clauses=sql.Composed(clauses))


def _publish(conn: psycopg.Connection, load_id: int, fault: str | None) -> dict[str, Change]:
    """Turn every core table into the new version in one transaction.

    The load is marked succeeded inside the same transaction, so the status row is the commit marker
    that confirm_publish() reads when the reply to COMMIT is lost. Foreign keys are deferred to the
    commit (sql/core/02_keys.sql): the MERGEs can then run in any order, and the complete new version
    is checked once.
    """
    statements = publish_statements(conn)
    changes = {}
    with conn.transaction():
        conn.execute(sql.SQL("SET LOCAL lock_timeout = {}").format(sql.Literal(PUBLISH_LOCK_TIMEOUT)))
        conn.execute("SET CONSTRAINTS ALL DEFERRED")
        for table, statement in statements:
            changes[table] = Change(*conn.execute(statement).fetchone())
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO meta.load_changes (load_id, table_name, inserted, updated, deleted)"
                " VALUES (%s, %s, %s, %s, %s)",
                [(load_id, table, *change) for table, change in changes.items()],
            )
        if fault == "publish":
            raise InjectedFault("fault injected inside the publish transaction, before commit")
        conn.execute(
            "UPDATE meta.load_runs SET status = 'succeeded', finished_at = clock_timestamp() WHERE load_id = %s",
            (load_id,),
        )
        if fault == "lost_before_commit":
            _drop_connection(conn)
    if fault == "lost_after_commit":
        _drop_connection(conn)
    return changes


def _drop_connection(conn: psycopg.Connection) -> None:
    """The server ends this session; the client sees the error a lost connection gives."""
    conn.execute("SELECT pg_terminate_backend(pg_backend_pid())")


def confirm_publish(target: Target, load_id: int, backend: tuple, timeout: float = CONFIRM_TIMEOUT_S) -> str:
    """Establish from a new connection whether the publish of `load_id` committed.

    `backend` is (pid, backend_start) of the session that ran the publish. 'succeeded' in
    meta.load_runs proves the commit. Its absence proves nothing while that session still exists,
    since the server may still be committing; once the session is gone, its transaction is over and
    the status row is final. Returns 'published', 'not_published' or 'unknown' (no answer in time).

    Everything is bounded by the deadline `timeout` seconds from now: each statement, the target
    verification included, is cancelled by the server when it is reached, so a status read waiting for
    a lock on meta.load_runs ends there too. Only a connection attempt pending at the deadline can
    overrun it, by up to 2 s per address (see db.connect).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with db.connect(target, deadline=deadline) as conn:
                while True:
                    # The session check comes first: if it was already gone, the status read after it
                    # is final.
                    db.bound_next_statement(conn, deadline)
                    alive = conn.execute(
                        "SELECT EXISTS (SELECT FROM pg_stat_activity WHERE pid = %s AND backend_start = %s)", backend
                    ).fetchone()[0]
                    db.bound_next_statement(conn, deadline)
                    status = conn.execute("SELECT status FROM meta.load_runs WHERE load_id = %s", (load_id,)).fetchone()
                    if status == ("succeeded",):
                        return "published"
                    if not alive:
                        return "not_published"
                    time.sleep(max(0.0, min(0.1, deadline - time.monotonic())))
        except (psycopg.Error, config.ConfigError, db.DeadlinePassed):
            time.sleep(max(0.0, min(0.5, deadline - time.monotonic())))
    return "unknown"


def recorded_changes(conn: psycopg.Connection, load_id: int) -> dict[str, Change]:
    rows = conn.execute(
        "SELECT table_name, inserted, updated, deleted FROM meta.load_changes WHERE load_id = %s ORDER BY table_name",
        (load_id,),
    )
    return {table: Change(*counts) for table, *counts in rows}


def _maintain(conn: psycopg.Connection) -> list[str]:
    """Refresh planner statistics and the visibility map of core after a publish.

    The new version is already committed, so a failure here is returned as a cleanup error rather than
    raised: it changes nothing about what was published.
    """
    try:
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'core' ORDER BY 1")]
        conn.execute(sql.SQL("VACUUM (ANALYZE) {}").format(sql.SQL(", ").join(sql.Identifier("core", t) for t in tables)))
    except Exception as exc:
        return [f"VACUUM (ANALYZE) of core failed: {type(exc).__name__}: {exc}"]
    return []


def _release_lock(conn: psycopg.Connection) -> tuple[str, ...]:
    """Release the loader lock; a failure is returned, never raised, so it cannot mask the outcome."""
    try:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    except Exception as exc:
        # On a broken connection the lock ends with the server session.
        return (f"releasing the loader lock failed: {type(exc).__name__}: {exc}",)
    return ()


def _mark_failed(conn: psycopg.Connection, load_id: int, exc: Exception) -> None:
    with _BOOKKEEPING_ERRORS:
        conn.execute(
            "UPDATE meta.load_runs SET status = 'failed', finished_at = clock_timestamp(), error = %s"
            " WHERE load_id = %s AND status = 'running'",
            (f"{type(exc).__name__}: {exc}".strip(), load_id),
        )


def table_checksums(conn: psycopg.Connection, schema: str = "core") -> dict[str, tuple[int, str]]:
    """Row count and an order-independent md5 of every table in `schema`.

    Rows are sorted by their text form, which is deterministic under the builtin C.UTF-8 collation
    (sql/bootstrap/bootstrap.sql), so equal data gives equal checksums on any platform.
    """
    tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1", (schema,))]
    result = {}
    for table in tables:
        query = sql.SQL(
            "SELECT count(*), md5(coalesce(string_agg(t::text, E'\\n' ORDER BY t::text), '')) FROM {} AS t"
        ).format(sql.Identifier(schema, table))
        count, digest = conn.execute(query).fetchone()
        result[table] = (count, digest)
    return result
