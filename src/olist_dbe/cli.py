"""Command line: olist-dbe <command>  (or: python -m olist_dbe <command>).

Every command that touches the database works on the main project database (OLIST_DBE_DB) and first
verifies that the connection really reaches it (src/olist_dbe/db.py); `check` shows that verification.
The exception is `bootstrap`, which runs sql/bootstrap/bootstrap.sql through psql as a superuser.

Exit status: 0 success, 1 error (nothing was published), 3 the outcome of a publish is unknown.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import conninfo

from . import bench, config, db, load, queries, report

EVAL_DATABASES = ("olist_blind_eval_v1", "olist_abcd40_snapshot_v1")
PROJECT_DATABASES = ("olist_dbe", "olist_dbe_test")
BOOTSTRAP_SQL = config.SQL_DIR / "bootstrap" / "bootstrap.sql"


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Run bootstrap.sql with psql against exactly the given server and administration database.

    Every PG* variable except PGPASSFILE is removed from psql's environment and psqlrc is skipped, so
    neither can redirect the session (PGHOSTADDR, PGSERVICE), alter it (PGOPTIONS) or run commands of
    its own. The script then checks the port and database it actually reached.
    """
    psql = args.psql or config.pg_program("psql")
    options = {"options": "-c default_transaction_read_only=on"} if args.dry_run else {}
    target = conninfo.make_conninfo(host=args.host, port=args.port, dbname=args.admin_db, user=args.admin_user,
                                    application_name="olist_dbe_bootstrap", **options)
    removed = sorted(name for name in os.environ if name.upper().startswith("PG") and name.upper() != "PGPASSFILE")
    environment = {name: value for name, value in os.environ.items() if name not in removed}
    print(f"bootstrap  {args.admin_user}@{args.host}:{args.port}/{args.admin_db}"
          + (" (dry run in a read-only session)" if args.dry_run else ""))
    if removed:
        print(f"           not passed to psql: {', '.join(removed)}")
    sys.stdout.flush()
    status = subprocess.run(
        [psql, "--no-psqlrc", "--set=ON_ERROR_STOP=1", f"--set=expected_port={args.port}",
         f"--set=admin_db={args.admin_db}", f"--set=adopt={','.join(args.adopt)}",
         f"--set=dry_run={'on' if args.dry_run else 'off'}", f"--dbname={target}", f"--file={BOOTSTRAP_SQL}"],
        env=environment,
    ).returncode
    if status != 0:
        print(f"error: bootstrap did not complete (psql exit status {status})", file=sys.stderr)
        return 1
    return 0


def database_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_$.-]+", value):
        raise argparse.ArgumentTypeError(f"not a plain database name: {value!r}")
    return value


def cmd_check(args: argparse.Namespace) -> int:
    target = config.test_target() if args.test else config.main_target()
    with db.connect(target, verify=False) as conn:
        problems = db.target_problems(target, db.observe(conn))
        version, database, user, provider, locale = conn.execute(
            "SELECT current_setting('server_version'), current_database(), current_user,"
            " datlocprovider, datlocale FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        print(f"server     PostgreSQL {version}")
        print(f"database   {database} as {user}")
        print(f"collation  provider={provider} locale={locale}")
        for name, can_connect in conn.execute(
            "SELECT datname, has_database_privilege(datname, 'CONNECT') FROM pg_database"
            " WHERE datname = ANY(%s) ORDER BY datname",
            (list(EVAL_DATABASES),),
        ):
            note = "reachable from this login" if can_connect else "not reachable"
            print(f"isolation  {name}: {note}")
    print(f"target     {target}: " + ("verified" if not problems else "REFUSED"))
    for problem in problems:
        print(f"           - {problem}")
    return 1 if problems else 0


def cmd_init(args: argparse.Namespace) -> int:
    with db.connect(config.main_target()) as conn:
        db.init_schemas(conn, recreate_core=args.recreate_core)
    print("schemas meta, raw, dq and core are in place" + (" (core recreated empty)" if args.recreate_core else ""))
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    data_dir = args.data_dir or config.data_dir()
    result = load.run_load(data_dir, target=config.main_target())
    print(f"load {result.load_id} published"
          + (" (confirmed over a new connection after the connection broke)" if result.confirmed_after_disconnect else ""))
    print(f"  {'table':<25} {'inserted':>9} {'updated':>9} {'deleted':>9}")
    for table, change in result.changes.items():
        print(f"  core.{table:<20} {change.inserted:>9,} {change.updated:>9,} {change.deleted:>9,}")
    for problem in result.cleanup_errors:
        print(f"warning: after the commit: {problem}", file=sys.stderr)
    return 0


def cmd_publish_sql(args: argparse.Namespace) -> int:
    with db.connect(config.main_target()) as conn:
        for table, statement in load.publish_statements(conn):
            print(f"-- core.{table}\n{statement.as_string(conn)};\n")
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    data_dir = args.data_dir or config.data_dir()
    text = json.dumps(load.manifest(load.inspect_files(data_dir)), indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


def cmd_dq_report(args: argparse.Namespace) -> int:
    with db.connect(config.main_target()) as conn:
        load_id = args.load_id or report.latest_load_id(conn)
        if load_id is None:
            print("no finished load yet", file=sys.stderr)
            return 1
        text = report.render_dq_report(conn, load_id)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_queries(args: argparse.Namespace) -> int:
    with db.connect(config.main_target()) as conn:
        if args.out:
            for query, rows, digest in queries.write_results(conn, args.out):
                print(f"{query.name:<30} {rows:>6,} rows  {digest[:16]}")
            print(f"wrote {args.out}")
            return 0
        for query in queries.all_queries():
            columns, rows = queries.execute(conn, query.text, query.params)
            print(f"{query.name:<30} {len(rows):>6,} rows  {queries.fingerprint(columns, rows)[:16]}")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    experiments = bench.load_experiments()
    if args.experiment:
        unknown = set(args.experiment) - {e.id for e in experiments}
        if unknown:
            print(f"error: no experiment {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1
        experiments = [e for e in experiments if e.id in args.experiment]
    with db.connect(config.main_target()) as conn:
        record = bench.run(conn, experiments, warmup=args.warmup, repeat=args.repeat)
    path = bench.save(record, args.out)
    print(f"wrote {path}")
    differing = [f"{e['id']} {v['label']}" for e in record["experiments"] for v in e["variants"] if not v["matches_reference"]]
    for name in differing:
        print(f"error: {name}: the result differs from the reference variant's", file=sys.stderr)
    return 1 if differing else 0


def cmd_bench_report(args: argparse.Namespace) -> int:
    text = bench.render_report(bench.load_runs(args.runs), bench.load_experiments())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    with db.connect(config.main_target()) as conn:
        for load_id, status, started, finished, error in conn.execute(
            "SELECT load_id, status, started_at, finished_at, error FROM meta.load_runs ORDER BY load_id DESC LIMIT 5"
        ):
            took = f"{(finished - started).total_seconds():.1f}s" if finished else "-"
            print(f"load {load_id:>4}  {status:<9} {started:%Y-%m-%d %H:%M}  {took:>7}  {error or ''}")
        for table, (rows, digest) in load.table_checksums(conn).items():
            print(f"core.{table:<20} {rows:>9,}  md5 {digest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olist-dbe", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bootstrap", help="create or verify the roles and databases, as a superuser (psql)")
    p.add_argument("--port", type=int, required=True, help="the server's port; the script checks the one it reaches")
    p.add_argument("--admin-db", type=database_name, required=True,
                   help="administration database to connect to (e.g. postgres); never a project database")
    p.add_argument("--host", default="localhost")
    p.add_argument("--admin-user", default="postgres", help="a superuser")
    p.add_argument("--adopt", action="append", default=[], choices=PROJECT_DATABASES,
                   help="mark this existing, unmarked database as the project's after checking it (repeatable)")
    p.add_argument("--dry-run", action="store_true", help="run every check and show the plan, in a read-only session")
    p.add_argument("--psql", help="path of psql (default: OLIST_DBE_PG_BIN, then PATH)")
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser("check", help="show server, collation, isolation from the eval databases, and target verification")
    p.add_argument("--test", action="store_true", help="check the test database (OLIST_DBE_TEST_DB) instead")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("init", help="create the schemas and the core tables (safe to re-run)")
    p.add_argument("--recreate-core", action="store_true",
                   help="drop and recreate core (empty) after a change to sql/core/0*.sql; reload afterwards")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("load", help="load the CSV files and publish them into core")
    p.add_argument("--data-dir", type=Path, help="defaults to OLIST_DATA_DIR")
    p.set_defaults(func=cmd_load)

    sub.add_parser("publish-sql", help="print the MERGE statements a load runs to publish").set_defaults(func=cmd_publish_sql)

    p = sub.add_parser("manifest", help="SHA-256 and size of the source files as JSON")
    p.add_argument("--data-dir", type=Path, help="defaults to OLIST_DATA_DIR")
    p.add_argument("--out", type=Path, help="write to this file (e.g. data_manifest.json) instead of stdout")
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("dq-report", help="render the data-quality report of a load as Markdown")
    p.add_argument("--load-id", type=int, help="defaults to the latest finished load")
    p.add_argument("--out", type=Path, help="write to this file instead of stdout")
    p.set_defaults(func=cmd_dq_report)

    p = sub.add_parser("queries", help="run the business queries (sql/queries) with their declared parameters")
    p.add_argument("--out", type=Path, help="write each full result as CSV and a README.md to this folder")
    p.set_defaults(func=cmd_queries)

    p = sub.add_parser("bench", help="run the benchmark experiments (sql/bench/experiments.toml); creates and drops indexes")
    p.add_argument("--experiment", action="append", metavar="ID", help="run only this experiment (repeatable)")
    p.add_argument("--warmup", type=int, default=3, help="untimed runs per variant (default 3)")
    p.add_argument("--repeat", type=int, default=20, help="timed runs per variant, client and server each (default 20)")
    p.add_argument("--out", type=Path, default=bench.RUNS_DIR, help="folder for the run record (default docs/benchmarks/runs)")
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("bench-report", help="render the benchmark report from the run records")
    p.add_argument("--runs", type=Path, default=bench.RUNS_DIR)
    p.add_argument("--out", type=Path, default=bench.REPORT_FILE)
    p.set_defaults(func=cmd_bench_report)

    sub.add_parser("status", help="recent loads and core row counts and checksums").set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except load.PublishOutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        return 3
    except (load.LoadError, config.ConfigError, bench.BenchError, psycopg.Error) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
