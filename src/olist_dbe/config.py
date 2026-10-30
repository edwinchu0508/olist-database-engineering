"""Runtime configuration: where the project's databases are, and where the source files are.

Connection settings use project-specific variable names (OLIST_DBE_*) and are passed to libpq
explicitly, so PGHOST, PGDATABASE, PGUSER and similar variables left over from another project in the
same terminal cannot redirect this package. Values come from the environment, then from the .env
file in the repository root, then from the defaults below.

The password is never configured here: libpq reads it from pgpass.conf.
"""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = REPO_ROOT / "sql"
ENV_FILE = REPO_ROOT / ".env"

DEFAULTS = {
    "OLIST_DBE_HOST": "localhost",
    "OLIST_DBE_PORT": "5432",
    "OLIST_DBE_USER": "dbe_owner",
    "OLIST_DBE_DB": "olist_dbe",
    "OLIST_DBE_TEST_DB": "olist_dbe_test",
}

# libpq variables that would still change an explicitly specified connection: PGHOSTADDR replaces the
# address that `host` resolves to, PGSERVICE can supply hostaddr and options, and PGOPTIONS can switch
# the role (-c role=...). The package refuses to run while any of them is set.
OVERRIDING_LIBPQ_VARIABLES = ("PGHOSTADDR", "PGSERVICE", "PGOPTIONS")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Target:
    """A project database and the purpose marker it must carry (set by sql/bootstrap/bootstrap.sql)."""
    host: str
    port: int
    dbname: str
    user: str
    purpose: str  # 'main' or 'test'

    def __str__(self) -> str:
        return f"{self.user}@{self.host}:{self.port}/{self.dbname} ({self.purpose})"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Set KEY=VALUE pairs from `path` without overriding variables that are already set."""
    if not path.exists():
        return
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ConfigError(f"{path.name}:{lineno}: expected KEY=VALUE")
        key = key.strip()
        if key == "PGPASSWORD":
            raise ConfigError(f"{path.name}:{lineno}: put the password in pgpass.conf, not in {path.name}")
        if key.startswith("PG"):
            raise ConfigError(f"{path.name}:{lineno}: {key} is not used; use the OLIST_DBE_* names in .env.example")
        os.environ.setdefault(key, value.strip())


def setting(name: str) -> str:
    load_env_file()
    return os.environ.get(name) or DEFAULTS[name]


def check_libpq_environment() -> None:
    present = [name for name in OVERRIDING_LIBPQ_VARIABLES if os.environ.get(name)]
    if present:
        raise ConfigError(f"unset {', '.join(present)}: it can redirect or alter the project's connections")


def _target(dbname: str, purpose: str) -> Target:
    port = setting("OLIST_DBE_PORT")
    if not port.isdigit():
        raise ConfigError(f"OLIST_DBE_PORT must be a number, not {port!r}")
    return Target(setting("OLIST_DBE_HOST"), int(port), dbname, setting("OLIST_DBE_USER"), purpose)


def main_target() -> Target:
    return _target(setting("OLIST_DBE_DB"), "main")


def test_target() -> Target:
    dbname = setting("OLIST_DBE_TEST_DB")
    if not dbname.endswith("_test"):
        raise ConfigError(f"OLIST_DBE_TEST_DB must end in _test, not {dbname!r}")
    return _target(dbname, "test")


def pg_program(name: str) -> str:
    """A PostgreSQL program (psql, initdb, ...): from OLIST_DBE_PG_BIN if that is set, else from PATH."""
    load_env_file()
    bindir = os.environ.get("OLIST_DBE_PG_BIN")
    if bindir:
        for candidate in (Path(bindir) / f"{name}.exe", Path(bindir) / name):
            if candidate.is_file():
                return str(candidate)
        raise ConfigError(f"{name} not found in OLIST_DBE_PG_BIN ({bindir})")
    found = shutil.which(name)
    if not found:
        raise ConfigError(f"{name} not found on PATH; set OLIST_DBE_PG_BIN to PostgreSQL's bin folder")
    return found


def data_dir() -> Path:
    load_env_file()
    value = os.environ.get("OLIST_DATA_DIR")
    if not value:
        raise ConfigError("OLIST_DATA_DIR is not set (see .env.example)")
    path = Path(value)
    if not path.is_dir():
        raise ConfigError(f"OLIST_DATA_DIR does not exist: {path}")
    return path
