"""Data-quality checks.

Each check is one SQL file under sql/dq/<severity>/ that returns the violating rows, so any check
can be run by hand in psql. The first comment block of the file is its description.

- blocking: preconditions of the publish. Any violation (or an error) stops the load.
- warning: known anomalies of the source data. Recorded and reported; the load continues.
"""
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from . import config

SEVERITIES = ("blocking", "warning")
SAMPLE_ROWS = 5


@dataclass(frozen=True)
class Check:
    name: str
    severity: str
    description: str
    sql: str


@dataclass(frozen=True)
class Result:
    check: Check
    status: str  # pass | warn | fail | error
    violations: int | None
    sample: list | None
    error: str | None
    duration_ms: int


def _parse(path: Path, severity: str) -> Check:
    text = path.read_text(encoding="utf-8")
    comment, body = [], []
    for line in text.splitlines():
        if not body and line.startswith("--"):
            comment.append(line.removeprefix("--").strip())
        else:
            body.append(line)
    sql = "\n".join(body).strip().rstrip(";")
    return Check(path.stem, severity, " ".join(comment), sql)


def discover(sql_dir: Path = config.SQL_DIR / "dq") -> list[Check]:
    checks = []
    for severity in SEVERITIES:
        checks += [_parse(p, severity) for p in sorted((sql_dir / severity).glob("*.sql"))]
    return checks


def run_check(conn: psycopg.Connection, check: Check) -> Result:
    started = time.perf_counter()
    try:
        with conn.transaction():
            violations = conn.execute(f"SELECT count(*) FROM ({check.sql}) AS v").fetchone()[0]
            sample = conn.execute(
                f"SELECT coalesce(jsonb_agg(row_json), '[]') FROM ("
                f" SELECT to_jsonb(v) AS row_json FROM ({check.sql}) AS v"
                f" ORDER BY to_jsonb(v)::text LIMIT {SAMPLE_ROWS}) AS s"
            ).fetchone()[0]
    except psycopg.Error as exc:
        return Result(check, "error", None, None, str(exc).strip(), _ms_since(started))
    if violations == 0:
        status = "pass"
    else:
        status = "fail" if check.severity == "blocking" else "warn"
    return Result(check, status, violations, sample, None, _ms_since(started))


def run_checks(conn: psycopg.Connection, load_id: int) -> list[Result]:
    """Run every check against raw.* and record the results under `load_id`."""
    results = [run_check(conn, check) for check in discover()]
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO dq.check_results"
            " (load_id, check_name, severity, status, violations, sample, error, duration_ms)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (load_id, r.check.name, r.check.severity, r.status, r.violations,
                 None if r.sample is None else Jsonb(r.sample), r.error, r.duration_ms)
                for r in results
            ],
        )
    return results


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
