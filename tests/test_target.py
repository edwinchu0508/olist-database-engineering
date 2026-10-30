"""Every connection is checked against its intended target before anything is written."""
import dataclasses

import psycopg
import pytest

from olist_dbe import config, db

MATCHING = {
    "host": "localhost", "port": 5432, "database": "olist_dbe_test", "session_user": "dbe_owner",
    "current_user": "dbe_owner", "superuser": False, "purpose": "test",
}
TARGET = config.Target("localhost", 5432, "olist_dbe_test", "dbe_owner", "test")


@pytest.mark.parametrize(("change", "problem"), [
    pytest.param({}, None, id="matching"),
    pytest.param({"port": 5433}, "endpoint is localhost:5433", id="other endpoint"),
    pytest.param({"database": "olist_blind_eval_v1"}, "database is 'olist_blind_eval_v1'", id="other database"),
    pytest.param({"session_user": "postgres", "current_user": "postgres"}, "role is 'postgres'", id="other role"),
    pytest.param({"current_user": "dbe_reader"}, "current 'dbe_reader'", id="switched role"),
    pytest.param({"superuser": True}, "superuser", id="superuser"),
    pytest.param({"purpose": None}, "database has no marker", id="no marker"),
    pytest.param({"purpose": "main"}, "marker 'main'", id="main database"),
])
def test_target_problems(change, problem):
    problems = db.target_problems(TARGET, MATCHING | change)
    if problem is None:
        assert problems == []
    else:
        assert len(problems) == 1 and problem in problems[0]


def test_connection_to_a_database_with_another_purpose_is_refused(target):
    with pytest.raises(db.TargetMismatch, match="expected olist_dbe.purpose='main'"):
        db.connect(dataclasses.replace(target, purpose="main"))


def test_connection_to_an_unmarked_database_is_refused(target):
    try:
        with pytest.raises(db.TargetMismatch, match="database has no marker"):
            db.connect(dataclasses.replace(target, dbname="postgres"))
    except psycopg.OperationalError as exc:  # the role may not be allowed to connect there at all
        pytest.skip(f"cannot connect to postgres: {exc}")


def test_marker_is_read_from_the_catalog_not_the_session(target):
    """A client-side setting cannot impersonate a database's purpose."""
    with psycopg.connect(host=target.host, port=target.port, dbname=target.dbname, user=target.user,
                         options="-c olist_dbe.purpose=main", autocommit=True) as conn:
        assert conn.execute("SELECT current_setting('olist_dbe.purpose')").fetchone()[0] == "main"
        assert db.observe(conn)["purpose"] == "test"


def test_stale_libpq_variables_do_not_redirect_connections(target, monkeypatch):
    monkeypatch.setenv("PGDATABASE", "postgres")
    monkeypatch.setenv("PGUSER", "postgres")
    monkeypatch.setenv("PGPORT", "1")
    with db.connect(target) as conn:
        seen = db.observe(conn)
    assert (seen["database"], seen["session_user"], seen["port"]) == (target.dbname, target.user, target.port)


@pytest.mark.parametrize("name", config.OVERRIDING_LIBPQ_VARIABLES)
def test_variables_that_override_explicit_parameters_are_refused(target, monkeypatch, name):
    monkeypatch.setenv(name, "-c role=dbe_reader" if name == "PGOPTIONS" else "x")
    with pytest.raises(config.ConfigError, match=name):
        db.connect(target)


def test_test_database_name_must_end_in_test(monkeypatch):
    monkeypatch.setenv("OLIST_DBE_TEST_DB", "olist_dbe")
    with pytest.raises(config.ConfigError, match="must end in _test"):
        config.test_target()


@pytest.mark.parametrize(("line", "message"), [
    ("PGPASSWORD=secret", "pgpass.conf"),
    ("PGHOST=elsewhere", "OLIST_DBE_"),
    ("no separator", "KEY=VALUE"),
])
def test_env_file_refuses_passwords_and_libpq_names(tmp_path, line, message):
    env = tmp_path / ".env"
    env.write_text(f"# comment\n{line}\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match=message):
        config.load_env_file(env)
