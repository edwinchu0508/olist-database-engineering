"""What a recorded result was produced with: code version, client, server settings, data.

Shared by the test run records (tests/run_report.py) and the benchmark runs (bench.py).
"""
import hashlib
import platform

import psycopg

from . import config

SERVER_SETTINGS = (
    "server_version", "server_encoding", "TimeZone", "lc_messages", "data_checksums", "fsync",
    "synchronous_commit", "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size",
    "random_page_cost", "effective_io_concurrency", "max_parallel_workers_per_gather", "jit",
)
CODE_GLOBS = ("src/**/*.py", "sql/**/*.sql", "sql/**/*.toml", "tests/**/*.py", "pyproject.toml", "data_manifest.json")


def code_fingerprint() -> str:
    """SHA-256 over the project's code, SQL and manifest (paths and contents), to tie a run to a version."""
    digest = hashlib.sha256()
    paths = sorted({p for pattern in CODE_GLOBS for p in config.REPO_ROOT.glob(pattern) if "__pycache__" not in p.parts})
    for path in paths:
        digest.update(path.relative_to(config.REPO_ROOT).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def client() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "psycopg": psycopg.__version__,
        "libpq": str(psycopg.pq.version()),
    }


def loaded_data(conn: psycopg.Connection) -> dict:
    """The data core holds: the latest successful load, and whether its source files matched data_manifest.json."""
    row = conn.execute(
        "SELECT r.load_id, r.finished_at,"
        " (SELECT coalesce(bool_and(f.matches_reference), false) FROM meta.load_files AS f WHERE f.load_id = r.load_id)"
        " FROM meta.load_runs AS r WHERE r.status = 'succeeded' ORDER BY r.load_id DESC LIMIT 1"
    ).fetchone()
    load_id, finished, files_match = row if row else (None, None, False)
    return {"load_id": load_id, "finished": finished, "files_match_reference": files_match}


def server(conn: psycopg.Connection) -> dict:
    """Version, locale, the selected settings, and every setting the server's configuration changed."""
    version = conn.execute("SELECT version()").fetchone()[0]
    provider, locale = conn.execute(
        "SELECT datlocprovider, datlocale FROM pg_database WHERE datname = current_database()"
    ).fetchone()
    # current_setting() gives values with their natural unit (4GB rather than 524288 8kB).
    selected = conn.execute(
        "SELECT name, current_setting(name) FROM pg_settings WHERE name = ANY(%s) ORDER BY name", (list(SERVER_SETTINGS),)
    ).fetchall()
    # Not at the built-in default, other than what this client's connection set.
    changed = conn.execute(
        "SELECT name, current_setting(name), source FROM pg_settings"
        " WHERE source NOT IN ('default', 'override', 'client', 'session') ORDER BY name"
    ).fetchall()
    return {
        "version": version,
        "locale": f"{provider} {locale}",
        "jit_available": conn.execute("SELECT pg_jit_available()").fetchone()[0],
        "settings": dict(selected),
        "changed_settings": [list(row) for row in changed],
    }
