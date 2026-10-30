"""Connections that are verified to reach the intended project database, and schema setup."""
import math
import time
from pathlib import Path

import psycopg

from . import config
from .config import Target

PURPOSE_SETTING = "olist_dbe.purpose"

# The purpose marker is read from the catalog, where only the database owner or a superuser can set it
# (ALTER DATABASE ... SET). current_setting() would also reflect a client-side override.
_OBSERVE_SQL = """
SELECT current_database(),
       session_user,
       current_user,
       r.rolsuper,
       (SELECT substr(cfg, length(%(prefix)s) + 1)
          FROM pg_db_role_setting AS s, unnest(s.setconfig) AS cfg
         WHERE s.setdatabase = d.oid AND s.setrole = 0 AND starts_with(cfg, %(prefix)s))
FROM pg_database AS d
JOIN pg_roles AS r ON r.rolname = session_user
WHERE d.datname = current_database()
"""


class TargetMismatch(config.ConfigError):
    """The connection does not reach the database the operation was meant for."""


class DeadlinePassed(Exception):
    """No time is left before the deadline for another statement."""


def observe(conn: psycopg.Connection) -> dict:
    database, session_user, current_user, superuser, purpose = conn.execute(
        _OBSERVE_SQL, {"prefix": PURPOSE_SETTING + "="}
    ).fetchone()
    return {
        "host": conn.info.host,
        "port": int(conn.info.port),
        "database": database,
        "session_user": session_user,
        "current_user": current_user,
        "superuser": superuser,
        "purpose": purpose,
    }


def target_problems(target: Target, seen: dict) -> list[str]:
    """Every way in which the observed connection differs from `target`; empty when it matches."""
    problems = []
    if (seen["host"], seen["port"]) != (target.host, target.port):
        problems.append(f"endpoint is {seen['host']}:{seen['port']}, expected {target.host}:{target.port}")
    if seen["database"] != target.dbname:
        problems.append(f"database is {seen['database']!r}, expected {target.dbname!r}")
    if seen["session_user"] != target.user or seen["current_user"] != target.user:
        problems.append(
            f"role is {seen['session_user']!r} (current {seen['current_user']!r}), expected {target.user!r}")
    if seen["superuser"]:
        problems.append("refusing to work as a superuser")
    if seen["purpose"] != target.purpose:
        found = "no marker" if seen["purpose"] is None else f"marker {seen['purpose']!r}"
        problems.append(f"database has {found}, expected {PURPOSE_SETTING}={target.purpose!r}"
                        " (set by sql/bootstrap/bootstrap.sql)")
    return problems


def bound_next_statement(conn: psycopg.Connection, deadline: float) -> None:
    """Make the server cancel the next statement on `conn` once `deadline` (time.monotonic()) passes.

    statement_timeout counts from the start of each statement and includes time spent waiting for
    locks, so it has to be set again, to the time that is left, before every statement.
    """
    left_ms = math.ceil((deadline - time.monotonic()) * 1000)
    if left_ms <= 0:  # 0 would disable the timeout
        raise DeadlinePassed("the deadline has passed")
    conn.execute("SELECT set_config('statement_timeout', %s, false)", (f"{left_ms}ms",))


def connect(target: Target, *, verify: bool = True, deadline: float | None = None) -> psycopg.Connection:
    """Connect to `target` with explicit parameters and, by default, refuse any mismatch.

    Autocommit is on, so every transaction in this package is an explicit `with conn.transaction():`
    block and its boundaries are visible in the code.

    With a `deadline` (time.monotonic()), the connection attempt is bounded by libpq's connect_timeout
    and the verification by bound_next_statement(). connect_timeout is in whole seconds, at least 2,
    and applies to each address libpq tries, so an attempt pending at the deadline can end that much
    later. Without a deadline an unreachable server can block for as long as the operating system
    retries.
    """
    config.check_libpq_environment()
    extra = {} if deadline is None else {"connect_timeout": max(2, math.ceil(deadline - time.monotonic()))}
    conn = psycopg.connect(
        host=target.host, port=target.port, dbname=target.dbname, user=target.user,
        application_name="olist_dbe", client_encoding="UTF8", autocommit=True, **extra,
    )
    if verify:
        try:
            if deadline is not None:
                bound_next_statement(conn, deadline)
            problems = target_problems(target, observe(conn))
        except BaseException:
            conn.close()
            raise
        if problems:
            conn.close()
            raise TargetMismatch(f"{target}: " + "; ".join(problems))
    return conn


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    conn.execute(path.read_text(encoding="utf-8"))


CORE_DDL_FILES = ("01_tables.sql", "02_keys.sql", "03_grants.sql")


def init_schemas(conn: psycopg.Connection, *, recreate_core: bool = False) -> None:
    """Create the persistent schemas, and core if it does not exist yet. Safe to re-run.

    core holds the same tables for the life of the database; loads change their rows, never the
    tables themselves. A change to sql/core/0*.sql therefore needs recreate_core (and a reload).
    """
    with conn.transaction():
        for path in sorted((config.SQL_DIR / "ddl").glob("*.sql")):
            run_sql_file(conn, path)
        exists = conn.execute("SELECT EXISTS (SELECT FROM pg_namespace WHERE nspname = 'core')").fetchone()[0]
        if exists and recreate_core:
            conn.execute("DROP SCHEMA core CASCADE")
            exists = False
        if not exists:
            conn.execute("CREATE SCHEMA core")
            conn.execute("SET LOCAL search_path = core")
            for name in CORE_DDL_FILES:
                run_sql_file(conn, config.SQL_DIR / "core" / name)
