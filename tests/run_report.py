"""pytest --run-report PATH: write a Markdown record of the test run.

The record is the evidence behind any result the docs quote: when and against what the suite ran,
with which versions, server settings, source files and code, and how each test ended. It holds no
credentials: the password lives in pgpass.conf and never passes through this package.
"""
import datetime
import platform
import subprocess
import time
from pathlib import Path

import psycopg
import pytest

from olist_dbe import config, db, load, provenance


def pytest_addoption(parser):
    parser.addoption("--run-report", type=Path, metavar="PATH", help="write a Markdown record of this run to PATH")


def pytest_configure(config):
    path = config.getoption("--run-report")
    if path:
        config.pluginmanager.register(RunReport(path, config.invocation_params.args), "olist_dbe_run_report")


class RunReport:
    def __init__(self, path: Path, args):
        self.path = path
        self.args = list(args)
        self.started = datetime.datetime.now(datetime.timezone.utc)
        self.clock = time.perf_counter()
        self.fingerprint = provenance.code_fingerprint()  # at the start: the code this run actually used
        self.outcomes: dict[str, list] = {}  # nodeid -> [outcome, seconds]

    def pytest_runtest_logreport(self, report):
        entry = self.outcomes.setdefault(report.nodeid, ["passed", 0.0])
        entry[1] += report.duration
        if report.failed:
            entry[0] = "failed" if report.when == "call" else f"error in {report.when}"
        elif report.skipped and entry[0] == "passed":
            entry[0] = "skipped"

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        elapsed = time.perf_counter() - self.clock
        totals: dict[str, int] = {}
        for outcome, _ in self.outcomes.values():
            totals[outcome] = totals.get(outcome, 0) + 1
        lines = [
            f"# Test run {self.started:%Y-%m-%d %H:%M:%S} UTC",
            "",
            f"- Command: `pytest {' '.join(self.args)}`",
            f"- Result: {', '.join(f'{n} {k}' for k, n in sorted(totals.items())) or 'no tests'}"
            f" in {elapsed:.1f} s (exit status {int(exitstatus)})",
            f"- Code fingerprint at start (SHA-256 of src, sql, tests, pyproject.toml, data_manifest.json; see provenance.py):"
            f" `{self.fingerprint}`",
            "",
            "## Client",
            "",
            f"- Python {platform.python_version()} on {platform.platform()}",
            f"- psycopg {psycopg.__version__}, libpq {psycopg.pq.version()}, pytest {pytest.__version__}",
            f"- PostgreSQL programs (psql for the bootstrap; initdb and pg_ctl for its test cluster): {self._programs()}",
            "",
        ]
        lines += self._server()
        lines += self._source_data()
        lines += ["## Tests", "", "| Test | Outcome | Seconds |", "|---|---|---:|"]
        lines += [f"| `{nodeid}` | {outcome} | {seconds:.2f} |" for nodeid, (outcome, seconds) in self.outcomes.items()]
        lines.append("")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _programs() -> str:
        try:
            psql = config.pg_program("psql")
            version = subprocess.run([psql, "--version"], capture_output=True, text=True, check=True).stdout.strip()
        except Exception as exc:
            return f"not found ({type(exc).__name__}: {exc})"
        return f"`{Path(psql).parent}` ({version})"

    def _server(self) -> list[str]:
        try:
            target = config.test_target()
            with db.connect(target) as conn:
                server = provenance.server(conn)
        except Exception as exc:
            return ["## Server", "", f"Not recorded: {type(exc).__name__}: {exc}", ""]
        provider, locale = server["locale"].split(" ", 1)
        lines = [
            "## Server",
            "",
            f"- Target: `{target}`, verified (endpoint, database, role, not a superuser, purpose marker)",
            f"- {server['version']}",
            f"- Database locale: provider `{provider}`, locale `{locale}`",
            "",
            "| Setting | Value |",
            "|---|---|",
        ]
        lines += [f"| {name} | {value} |" for name, value in server["settings"].items()]
        lines += ["", "Settings not at their built-in default:", "", "| Setting | Value | Source |", "|---|---|---|"]
        lines += [f"| {name} | {value} | {source} |" for name, value, source in server["changed_settings"]]
        return lines + [""]

    def _source_data(self) -> list[str]:
        try:
            data_dir = config.data_dir()
            files = load.manifest(load.inspect_files(data_dir))
        except Exception as exc:
            return ["## Source data", "", f"Not recorded: {type(exc).__name__}: {exc}", ""]
        reference = load.reference_manifest()
        differing = sorted(name for name in files if files[name] != reference.get(name))
        verdict = "all match data_manifest.json" if not differing else f"**differ from data_manifest.json**: {', '.join(differing)}"
        return ["## Source data", "", f"- {len(files)} files in `{data_dir}`: {verdict}", ""]
