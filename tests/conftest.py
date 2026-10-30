"""Shared fixtures.

Every database test runs against the test target (config.test_target(): OLIST_DBE_TEST_DB, default
olist_dbe_test), and every connection is verified before use: it must reach that database on the
configured endpoint, as the configured non-superuser role, and the database must carry the marker
olist_dbe.purpose = 'test' (sql/bootstrap/bootstrap.sql). The marker, not the _test suffix, is what
keeps the suite away from olist_dbe and the evaluation databases, and what permits it to drop and
rebuild core: the bootstrap sets it only on a database it created, or on one that passed its checks
and that the operator adopted.

The session starts from an empty core and loads the real dataset once; tests that need broken input
build a temporary copy of the source folder with individual files rewritten.
"""
import os
import shutil
from pathlib import Path

import pytest

from olist_dbe import config, db, load

pytest_plugins = ["run_report"]


@pytest.fixture(scope="session")
def target() -> config.Target:
    try:
        return config.test_target()
    except config.ConfigError as exc:
        pytest.exit(f"refusing to run: {exc}", returncode=2)


@pytest.fixture(scope="session")
def data_dir() -> Path:
    try:
        return config.data_dir()
    except config.ConfigError as exc:
        pytest.skip(f"no source data: {exc}")


@pytest.fixture(scope="session")
def conn(target):
    try:
        connection = db.connect(target)
    except db.TargetMismatch as exc:
        pytest.exit(f"refusing to run: {exc}", returncode=2)
    with connection:
        db.init_schemas(connection, recreate_core=True)
        yield connection


@pytest.fixture(scope="session")
def loaded(conn, data_dir, target) -> load.LoadResult:
    """The real dataset loaded once into the empty core."""
    return load.run_load(data_dir, target=target)


@pytest.fixture(scope="session")
def baseline_checksums(conn, loaded) -> dict:
    return load.table_checksums(conn)


@pytest.fixture(scope="session")
def local_copy(tmp_path_factory, data_dir) -> Path:
    """The source files copied once to local temp storage, so variants can hard-link them."""
    target = tmp_path_factory.mktemp("olist_source")
    for name in load.SOURCE_FILES.values():
        shutil.copy2(data_dir / name, target / name)
    return target


@pytest.fixture
def variant(tmp_path, local_copy):
    """make(**{file_name: edit}) -> a data folder equal to the source except for the edited files.

    `edit` maps the file's text to new text; bytes and line endings are otherwise preserved. Edited
    files are private copies; the others are hard links to the shared copy and must not be written.
    """
    def make(**edits) -> Path:
        unknown = set(edits) - set(load.SOURCE_FILES.values())
        assert not unknown, f"not a source file: {unknown}"
        for name in load.SOURCE_FILES.values():
            source, target = local_copy / name, tmp_path / name
            if name in edits:
                target.write_bytes(edits[name](source.read_bytes().decode("utf-8")).encode("utf-8"))
            else:
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copy2(source, target)
        return tmp_path

    return make


# One category translation changed: loading this updates exactly one row of core.
CATEGORY_QUERY = (
    "SELECT product_category_name_english FROM core.product_categories WHERE product_category_name = 'beleza_saude'"
)


@pytest.fixture
def renamed(variant) -> Path:
    return variant(**{"product_category_name_translation.csv":
                      lambda text: text.replace("beleza_saude,health_beauty", "beleza_saude,health_beauty_v2", 1)})


def last_run(conn) -> tuple[int, str, str | None]:
    return conn.execute("SELECT load_id, status, error FROM meta.load_runs ORDER BY load_id DESC LIMIT 1").fetchone()
