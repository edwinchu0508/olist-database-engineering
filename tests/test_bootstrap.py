"""sql/bootstrap/bootstrap.sql, run through `olist-dbe bootstrap`, on a PostgreSQL cluster of its own.

The bootstrap needs a superuser and creates roles and databases, so these tests never use a configured
server: the module creates a throwaway cluster with initdb (trust authentication, listening on
localhost only, on a free port) and stops it at the end; pytest's temporary directory holds it. They
are skipped when initdb, pg_ctl or psql cannot be found (OLIST_DBE_PG_BIN, then PATH).

Every refusal must leave the cluster exactly as it was: the checks run before the first change.
"""
import socket
import subprocess
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import sql

from olist_dbe import cli, config, db

PROJECT_DATABASES = ("olist_dbe", "olist_dbe_test")
BOTH = ("--adopt", "olist_dbe", "--adopt", "olist_dbe_test")


@dataclass(frozen=True)
class Cluster:
    port: int
    psql: str

    def admin(self, dbname: str = "postgres") -> psycopg.Connection:
        return psycopg.connect(host="localhost", port=self.port, dbname=dbname, user="postgres", autocommit=True)

    def bootstrap(self, *args: str, admin_db: str = "postgres", admin_user: str = "postgres") -> int:
        return cli.main(["bootstrap", "--port", str(self.port), "--admin-db", admin_db, "--admin-user", admin_user,
                         "--psql", self.psql, *args])

    def psql_file(self, *variables: str) -> int:
        """bootstrap.sql run by psql directly, with only the given -v variables."""
        command = [self.psql, "--no-psqlrc", f"--dbname=host=localhost port={self.port} dbname=postgres user=postgres"]
        command += [f"--set={v}" for v in variables] + [f"--file={cli.BOOTSTRAP_SQL}"]
        return subprocess.run(command, capture_output=True).returncode


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    try:
        initdb, pg_ctl, psql = (config.pg_program(name) for name in ("initdb", "pg_ctl", "psql"))
    except config.ConfigError as exc:
        pytest.skip(f"no PostgreSQL server programs: {exc}")
    data = tmp_path_factory.mktemp("bootstrap_cluster") / "data"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--locale-provider=builtin",
                    "--builtin-locale=C.UTF-8", "--lc-messages=C", "--no-instructions"], check=True, capture_output=True)
    # No pipes for pg_ctl start: the server it leaves running would inherit them.
    subprocess.run([pg_ctl, "-D", data, "-l", data / "server.log", "-o", f"-p {port} -c listen_addresses=localhost",
                    "-w", "start"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        yield Cluster(port, psql)
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture
def server(cluster):
    """The cluster without any of the project's roles and databases."""
    with cluster.admin() as conn:
        for name in (*PROJECT_DATABASES, "other"):
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        for role in ("dbe_owner", "dbe_reader"):
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
    return cluster


STATE_SQL = """
SELECT (SELECT json_agg(json_build_array(rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole) ORDER BY rolname)
          FROM pg_roles WHERE rolname IN ('dbe_owner', 'dbe_reader')),
       (SELECT json_agg(json_build_array(datname, pg_get_userbyid(datdba), datacl::text) ORDER BY datname)
          FROM pg_database WHERE datname IN ('olist_dbe', 'olist_dbe_test', 'other')),
       (SELECT json_agg(json_build_array(d.datname, s.setrole::regrole::text, s.setconfig) ORDER BY d.datname, s.setrole)
          FROM pg_db_role_setting AS s LEFT JOIN pg_database AS d ON d.oid = s.setdatabase),
       (SELECT json_agg(json_build_array(roleid::regrole::text, member::regrole::text) ORDER BY roleid, member)
          FROM pg_auth_members)
"""


def state(cluster: Cluster) -> tuple:
    with cluster.admin() as conn:
        return conn.execute(STATE_SQL).fetchone()


def markers(cluster: Cluster) -> dict:
    with cluster.admin() as conn:
        return dict(conn.execute(
            "SELECT d.datname, substr(cfg, length('olist_dbe.purpose=') + 1)"
            " FROM pg_db_role_setting AS s JOIN pg_database AS d ON d.oid = s.setdatabase, unnest(s.setconfig) AS cfg"
            " WHERE s.setrole = 0 AND starts_with(cfg, 'olist_dbe.purpose=')"
        ).fetchall())


def first_bootstrap(conn: psycopg.Connection) -> None:
    """What the first version of bootstrap.sql left behind: roles and databases, but no purpose markers."""
    conn.execute("CREATE ROLE dbe_owner LOGIN")
    conn.execute("CREATE ROLE dbe_reader NOLOGIN")
    conn.execute("GRANT dbe_reader TO dbe_owner")
    for name in PROJECT_DATABASES:
        conn.execute(f"CREATE DATABASE {name} OWNER dbe_owner TEMPLATE template0 ENCODING 'UTF8'"
                     " LOCALE_PROVIDER builtin BUILTIN_LOCALE 'C.UTF-8'")
        conn.execute(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC")


def test_creates_the_roles_and_marked_databases_and_a_rerun_changes_nothing(server):
    assert server.bootstrap() == 0
    after_first = state(server)
    assert server.bootstrap() == 0
    assert state(server) == after_first

    assert markers(server) == {"olist_dbe": "main", "olist_dbe_test": "test"}
    with server.admin() as conn:
        assert conn.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls"
            " FROM pg_roles WHERE rolname LIKE 'dbe\\_%' ORDER BY 1"
        ).fetchall() == [("dbe_owner", True, False, False, False, False, False),
                         ("dbe_reader", False, False, False, False, False, False)]
        assert conn.execute(
            "SELECT datname, pg_get_userbyid(datdba), datlocprovider, datlocale, has_database_privilege('public', datname, 'CONNECT')"
            " FROM pg_database WHERE datname LIKE 'olist\\_dbe%' ORDER BY 1"
        ).fetchall() == [("olist_dbe", "dbe_owner", "b", "C.UTF-8", False),
                         ("olist_dbe_test", "dbe_owner", "b", "C.UTF-8", False)]
    # The package accepts exactly these databases for their purpose.
    for name, purpose in (("olist_dbe", "main"), ("olist_dbe_test", "test")):
        target = config.Target("localhost", server.port, name, "dbe_owner", purpose)
        db.connect(target).close()


def test_dry_run_reports_the_plan_and_changes_nothing(server, capfd):
    before = state(server)
    assert server.bootstrap("--dry-run") == 0
    assert state(server) == before
    out = capfd.readouterr().out
    assert "role dbe_owner" in out and "create, mark 'test'" in out
    assert "Dry run: nothing was changed." in out


def test_unmarked_databases_are_adopted_only_when_named(server, capfd):
    """The state the first bootstrap left on the shared server: the operator reads the dry run's
    listing of each database, then names the ones that are the project's."""
    with server.admin() as conn:
        first_bootstrap(conn)
    before = state(server)

    assert server.bootstrap() == 1
    out = capfd.readouterr().out
    assert "database olist_dbe exists without a purpose marker" in out
    assert "--adopt olist_dbe_test" in out
    assert server.bootstrap("--adopt", "olist_dbe_test") == 1  # olist_dbe is still unmarked
    assert server.bootstrap(*BOTH, "--dry-run") == 0
    out = capfd.readouterr().out
    assert "Schemas in database olist_dbe_test" in out and "adopt (verified): mark 'test'" in out
    assert state(server) == before

    assert server.bootstrap(*BOTH) == 0
    assert markers(server) == {"olist_dbe": "main", "olist_dbe_test": "test"}


MISMATCHES = [
    # (id, statements on the administration database ("first": first_bootstrap()),
    #  (database, statements inside it) or None, expected message)
    ("database owned by another role",
     ["CREATE DATABASE olist_dbe_test TEMPLATE template0 LOCALE_PROVIDER builtin BUILTIN_LOCALE 'C.UTF-8'"],
     None, "database olist_dbe_test is owned by postgres, not dbe_owner"),
    ("database with another collation",
     ["CREATE ROLE dbe_owner LOGIN",
      "CREATE DATABASE olist_dbe_test OWNER dbe_owner TEMPLATE template0 LOCALE_PROVIDER libc LOCALE 'C'"],
     None, "not UTF8 and builtin C.UTF-8"),
    ("database marked for the other purpose",
     ["first", "ALTER DATABASE olist_dbe_test SET olist_dbe.purpose = 'main'"],
     None, "database olist_dbe_test is marked 'main', expected 'test'"),
    ("database with other settings",
     ["first", "ALTER DATABASE olist_dbe SET search_path = elsewhere"],
     None, "database olist_dbe has settings other than its marker: search_path=elsewhere"),
    ("schema this project does not create", ["first"],
     ("olist_dbe_test", "CREATE SCHEMA other_project"), "schema other_project is not one this project creates"),
    ("table in public", ["first"],
     ("olist_dbe", "CREATE TABLE public.notes (note text)"),
     "table public.notes, but this project creates nothing in public"),
    ("core table owned by another role", ["first"],
     ("olist_dbe_test", "CREATE SCHEMA core AUTHORIZATION dbe_owner", "CREATE TABLE core.orders (id int)"),
     "table core.orders is owned by postgres"),
    ("function", ["first"],
     ("olist_dbe", "CREATE SCHEMA meta AUTHORIZATION dbe_owner", "SET ROLE dbe_owner",
      "CREATE FUNCTION meta.f() RETURNS int LANGUAGE sql AS 'SELECT 1'"), "function meta.f()"),
    ("role with other attributes", ["CREATE ROLE dbe_owner LOGIN CREATEDB"],
     None, "role dbe_owner exists with other attributes: CREATEDB"),
    ("reader role that can log in", ["CREATE ROLE dbe_reader LOGIN"],
     None, "role dbe_reader exists with other attributes: LOGIN"),
    ("role with another membership", ["CREATE ROLE dbe_owner LOGIN", "GRANT pg_read_all_data TO dbe_owner"],
     None, "role dbe_owner is a member of pg_read_all_data"),
    ("role granted to another role", ["CREATE ROLE dbe_owner LOGIN", "CREATE ROLE someone", "GRANT dbe_owner TO someone"],
     None, "role dbe_owner is granted to someone"),
    ("role with settings", ["CREATE ROLE dbe_owner LOGIN", "ALTER ROLE dbe_owner SET search_path = elsewhere"],
     None, "role dbe_owner has settings: search_path=elsewhere"),
    ("role owning another database", ["CREATE ROLE dbe_owner LOGIN", "CREATE DATABASE other OWNER dbe_owner"],
     None, "role dbe_owner owns or has privileges on database other"),
    ("role with privileges in another database",
     ["CREATE ROLE dbe_reader NOLOGIN", "CREATE TABLE public.elsewhere (id int)", "GRANT SELECT ON public.elsewhere TO dbe_reader"],
     None, "role dbe_reader owns or has privileges on objects in database postgres"),
]


@pytest.mark.parametrize("admin_setup, inner_setup, message", [m[1:] for m in MISMATCHES], ids=[m[0] for m in MISMATCHES])
def test_refuses_a_mismatching_role_or_database_before_changing_anything(server, capfd, admin_setup, inner_setup, message):
    try:
        with server.admin() as conn:
            for statement in admin_setup:
                if statement == "first":
                    first_bootstrap(conn)
                else:
                    conn.execute(statement)
        if inner_setup:
            name, *statements = inner_setup
            with server.admin(name) as conn:
                for statement in statements:
                    conn.execute(statement)
        before = state(server)

        # --adopt never overrides a check; it only permits marking a database that passes them all.
        assert server.bootstrap(*BOTH) == 1
        out = capfd.readouterr().out
        assert "Bootstrap refused; nothing was changed:" in out
        assert message in out
        assert state(server) == before
    finally:
        with server.admin() as conn:
            conn.execute("DROP TABLE IF EXISTS public.elsewhere")
            conn.execute("DROP ROLE IF EXISTS someone")


def test_refuses_the_wrong_session(server, capfd):
    with server.admin() as conn:
        first_bootstrap(conn)
    before = state(server)

    assert server.bootstrap(*BOTH, admin_db="olist_dbe") == 1
    assert "olist_dbe cannot be the administration database" in capfd.readouterr().out
    assert server.bootstrap(*BOTH, admin_user="dbe_owner") == 1
    assert "connected as dbe_owner (current role dbe_owner), which is not a superuser" in capfd.readouterr().out
    # The script's own checks of what the session reached, whoever runs it.
    assert server.psql_file("expected_port=1", "admin_db=postgres") != 0
    assert server.psql_file(f"expected_port={server.port}", "admin_db=template1") != 0
    assert server.psql_file() != 0  # not run through the CLI at all
    assert state(server) == before


def test_connection_settings_in_the_environment_do_not_reach_psql(server, monkeypatch, capfd):
    monkeypatch.setenv("PGOPTIONS", "-c default_transaction_read_only=on")  # would make every change fail
    monkeypatch.setenv("PGSERVICE", "no_such_service")  # would make the connection fail
    monkeypatch.setenv("PGDATABASE", "olist_dbe")
    monkeypatch.setenv("PGPORT", "1")
    assert server.bootstrap() == 0
    not_passed = next(line for line in capfd.readouterr().out.splitlines() if "not passed to psql:" in line)
    assert {"PGDATABASE", "PGOPTIONS", "PGPORT", "PGSERVICE"} <= set(not_passed.split(":")[1].replace(",", " ").split())
    monkeypatch.undo()
    assert markers(server) == {"olist_dbe": "main", "olist_dbe_test": "test"}
