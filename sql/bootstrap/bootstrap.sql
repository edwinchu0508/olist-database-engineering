-- One-time setup of this project's roles and databases, as a superuser. Run it through the CLI, which
-- sets the psql variables checked below:
--
--   olist-dbe bootstrap --port 5432 --admin-db postgres --dry-run     (read-only: checks and plan)
--   olist-dbe bootstrap --port 5432 --admin-db postgres [--adopt NAME ...]
--
-- The CLI runs psql with explicit connection parameters, without psqlrc, and with every PG* variable
-- except PGPASSFILE removed from its environment, so PGOPTIONS, PGSERVICE, PGHOSTADDR and the like
-- cannot redirect or alter the session. --dry-run also makes the session read-only. Safe to re-run.
--
-- Creates, or verifies and keeps:
--   dbe_owner       login role; owns both databases, runs DDL and loads
--   dbe_reader      no-login role with read-only access to core; tests SET ROLE to it
--   olist_dbe       the project database, marker olist_dbe.purpose = 'main'
--   olist_dbe_test  the pytest database, marker 'test': the suite drops and rebuilds core in it
--
-- The package works only in a database that carries the expected marker. This script sets a marker
-- only on a database it creates, or on an existing one that passes every check and that the operator
-- names with --adopt after reading what it holds (the dry run lists it).
--
-- Before changing anything it checks, and refuses with the full list of problems:
--   - the session: the expected port and administration database, a superuser, current_user =
--     session_user; the administration database is none of the project or evaluation databases;
--   - existing roles of these names: only dbe_owner can log in, neither has SUPERUSER, CREATEDB,
--     CREATEROLE, REPLICATION or BYPASSRLS, the only membership is dbe_owner in dbe_reader, no role
--     settings, and nothing owned or granted outside the two project databases;
--   - existing databases of these names: owner dbe_owner, UTF8 with the builtin C.UTF-8 locale, no
--     settings other than the marker, the expected marker (or --adopt), and nothing that this project
--     does not create (check_database.sql).
-- It never alters an existing role or its password, and changes no other database.
--
-- Afterwards give dbe_owner a password in an interactive psql session (\password dbe_owner) and store
-- it with scripts/set_pgpass.ps1. No password is ever written to this repository.
--
-- Both databases use the builtin C.UTF-8 collation, so ORDER BY on text, and therefore every result
-- hash and table checksum, is identical on a Windows workstation and on a Linux CI runner.

\set ON_ERROR_STOP on
\set QUIET on
\if :{?expected_port}
\else
\echo 'bootstrap.sql: run it with olist-dbe bootstrap, which sets expected_port, admin_db, adopt and dry_run.'
DO $$ BEGIN RAISE EXCEPTION 'bootstrap.sql was run without the variables that olist-dbe bootstrap sets'; END $$;
\endif
\if :{?admin_db}
\else
DO $$ BEGIN RAISE EXCEPTION 'bootstrap.sql was run without the variables that olist-dbe bootstrap sets'; END $$;
\endif
\if :{?adopt}
\else
\set adopt ''
\endif
\if :{?dry_run}
\else
\set dry_run off
\endif
\set main_problems ''
\set test_problems ''

SET search_path = pg_catalog, pg_temp;

-- The session, the roles and the databases, as seen from the administration database.
WITH expected_role (name, login) AS (VALUES ('dbe_owner', true), ('dbe_reader', false)),
expected_db (name, purpose) AS (VALUES ('olist_dbe', 'main'), ('olist_dbe_test', 'test')),
adopt (name) AS (SELECT unnest(string_to_array(:'adopt', ','))),
role AS (SELECT r.*, e.login FROM pg_roles AS r JOIN expected_role AS e ON e.name = r.rolname),
db AS (
    SELECT d.*, e.purpose,
           (SELECT substr(cfg, length('olist_dbe.purpose=') + 1)
              FROM pg_db_role_setting AS s CROSS JOIN LATERAL unnest(s.setconfig) AS cfg
             WHERE s.setdatabase = d.oid AND s.setrole = 0 AND starts_with(cfg, 'olist_dbe.purpose=')) AS marker
      FROM pg_database AS d JOIN expected_db AS e ON e.name = d.datname
),
problem (problem) AS (
    SELECT format('connected to port %s, expected %s', current_setting('port'), :'expected_port')
     WHERE current_setting('port') <> :'expected_port'
    UNION ALL
    SELECT format('connected to database %I, expected %I', current_database(), :'admin_db')
     WHERE current_database() <> :'admin_db'
    UNION ALL
    SELECT format('%I cannot be the administration database', :'admin_db')
     WHERE :'admin_db' IN ('olist_dbe', 'olist_dbe_test', 'olist_blind_eval_v1', 'olist_abcd40_snapshot_v1')
    UNION ALL
    SELECT format('connected as %I (current role %I), which is not a superuser', session_user, current_user)
     WHERE current_user <> session_user OR NOT (SELECT rolsuper FROM pg_roles WHERE rolname = session_user)
    UNION ALL
    SELECT format('role %I exists with other attributes: %s', rolname, concat_ws(', ',
               CASE WHEN rolcanlogin AND NOT login THEN 'LOGIN' WHEN login AND NOT rolcanlogin THEN 'NOLOGIN' END,
               CASE WHEN rolsuper THEN 'SUPERUSER' END, CASE WHEN rolcreatedb THEN 'CREATEDB' END,
               CASE WHEN rolcreaterole THEN 'CREATEROLE' END, CASE WHEN rolreplication THEN 'REPLICATION' END,
               CASE WHEN rolbypassrls THEN 'BYPASSRLS' END))
      FROM role
     WHERE rolcanlogin <> login OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
    UNION ALL
    SELECT format('role %I is a member of %I', m.rolname, g.rolname)
      FROM pg_auth_members AS a JOIN role AS m ON m.oid = a.member JOIN pg_roles AS g ON g.oid = a.roleid
     WHERE (m.rolname, g.rolname) <> ('dbe_owner', 'dbe_reader')
    UNION ALL
    SELECT format('role %I is granted to %I', g.rolname, m.rolname)
      FROM pg_auth_members AS a JOIN role AS g ON g.oid = a.roleid JOIN pg_roles AS m ON m.oid = a.member
     WHERE m.rolname NOT IN (SELECT name FROM expected_role)
    UNION ALL
    SELECT format('role %I has settings: %s', r.rolname, array_to_string(s.setconfig, ', '))
      FROM pg_db_role_setting AS s JOIN role AS r ON r.oid = s.setrole
    UNION ALL
    -- Ownership and privileges anywhere in the cluster, other than on and inside the project databases.
    SELECT DISTINCT format('role %I owns or has privileges on %s', r.rolname,
               CASE WHEN s.dbid = 0 THEN pg_describe_object(s.classid, s.objid, s.objsubid)
                    ELSE format('objects in database %I', d.datname) END)
      FROM pg_shdepend AS s
      JOIN role AS r ON s.refclassid = 'pg_authid'::regclass AND s.refobjid = r.oid
      LEFT JOIN pg_database AS d ON d.oid = s.dbid
     WHERE s.dbid NOT IN (SELECT oid FROM db)
       AND NOT (s.dbid = 0 AND s.classid = 'pg_database'::regclass AND s.objid IN (SELECT oid FROM db))
    UNION ALL
    SELECT format('database %I is owned by %I, not dbe_owner', datname, pg_get_userbyid(datdba))
      FROM db WHERE pg_get_userbyid(datdba) <> 'dbe_owner'
    UNION ALL
    SELECT format('database %I has encoding %s and locale provider %s with %s, not UTF8 and builtin C.UTF-8',
                  datname, pg_encoding_to_char(encoding), datlocprovider, coalesce(datlocale, datcollate))
      FROM db
     WHERE pg_encoding_to_char(encoding) <> 'UTF8' OR datlocprovider <> 'b' OR datlocale IS DISTINCT FROM 'C.UTF-8'
    UNION ALL
    SELECT format('database %I is a template or does not allow connections', datname)
      FROM db WHERE datistemplate OR NOT datallowconn
    UNION ALL
    SELECT format('database %I has settings other than its marker: %s', d.datname, cfg)
      FROM db AS d JOIN pg_db_role_setting AS s ON s.setdatabase = d.oid CROSS JOIN LATERAL unnest(s.setconfig) AS cfg
     WHERE NOT (s.setrole = 0 AND starts_with(cfg, 'olist_dbe.purpose='))
    UNION ALL
    SELECT format('database %I is marked %L, expected %L', datname, marker, purpose)
      FROM db WHERE marker <> purpose
    UNION ALL
    SELECT format('database %I exists without a purpose marker. Check what it holds (--dry-run); if it is'
                  ' this project''s and may be rebuilt, name it with --adopt %s', datname, datname)
      FROM db WHERE marker IS NULL AND datname NOT IN (SELECT name FROM adopt)
    UNION ALL
    SELECT format('--adopt %s: not a database of this project', name)
      FROM adopt WHERE name NOT IN (SELECT name FROM expected_db)
    UNION ALL
    SELECT format('--adopt %s: no such database', name)
      FROM adopt WHERE name IN (SELECT name FROM expected_db) AND name NOT IN (SELECT datname FROM db)
)
SELECT coalesce(string_agg('  - ' || problem, E'\n'), '') AS cluster_problems,
       EXISTS (SELECT FROM db WHERE datname = 'olist_dbe' AND datallowconn AND NOT datistemplate) AS main_exists,
       EXISTS (SELECT FROM db WHERE datname = 'olist_dbe_test' AND datallowconn AND NOT datistemplate) AS test_exists
  FROM problem \gset

\echo
\echo 'Roles and databases of this project on this server:'
SELECT e.name AS role,
       CASE WHEN r.oid IS NULL THEN 'absent'
            ELSE concat_ws(' ', CASE WHEN r.rolcanlogin THEN 'LOGIN' ELSE 'NOLOGIN' END,
                           CASE WHEN r.rolsuper THEN 'SUPERUSER' END, CASE WHEN r.rolcreatedb THEN 'CREATEDB' END,
                           CASE WHEN r.rolcreaterole THEN 'CREATEROLE' END) END AS attributes
  FROM (VALUES ('dbe_owner'), ('dbe_reader')) AS e (name) LEFT JOIN pg_roles AS r ON r.rolname = e.name;
SELECT e.name AS database,
       coalesce(pg_get_userbyid(d.datdba), 'absent') AS owner,
       (SELECT substr(cfg, length('olist_dbe.purpose=') + 1)
          FROM pg_db_role_setting AS s CROSS JOIN LATERAL unnest(s.setconfig) AS cfg
         WHERE s.setdatabase = d.oid AND s.setrole = 0 AND starts_with(cfg, 'olist_dbe.purpose=')) AS marker,
       pg_size_pretty(pg_database_size(d.oid)) AS size,
       (SELECT count(*) FROM pg_stat_activity AS a WHERE a.datid = d.oid) AS sessions
  FROM (VALUES ('olist_dbe'), ('olist_dbe_test')) AS e (name) LEFT JOIN pg_database AS d ON d.datname = e.name;

-- What each existing project database holds. \connect reuses the host, port, user and options.
\if :main_exists
\connect -reuse-previous=on olist_dbe
\set db olist_dbe
\ir check_database.sql
SELECT :'db_problems' AS main_problems \gset
\endif
\if :test_exists
\connect -reuse-previous=on olist_dbe_test
\set db olist_dbe_test
\ir check_database.sql
SELECT :'db_problems' AS test_problems \gset
\endif
\connect -reuse-previous=on :admin_db
SET search_path = pg_catalog, pg_temp;

SELECT concat_ws(E'\n', nullif(:'cluster_problems', ''), nullif(:'main_problems', ''), nullif(:'test_problems', ''),
                 CASE WHEN current_database() <> :'admin_db' OR current_setting('port') <> :'expected_port'
                      THEN '  - the session did not return to the administration database' END) AS problems \gset
SELECT :'problems' = '' AS checks_passed \gset
\if :checks_passed
\else
\echo
\echo 'Bootstrap refused; nothing was changed:'
\echo :problems
DO $$ BEGIN RAISE EXCEPTION 'bootstrap refused; nothing was changed'; END $$;
\endif

\echo
\echo 'All checks passed. Plan:'
SELECT object, action FROM (
    SELECT 1 AS n, 'role ' || e.name AS object,
           CASE WHEN r.oid IS NULL THEN 'create' ELSE 'keep (verified)' END AS action
      FROM (VALUES ('dbe_owner'), ('dbe_reader')) AS e (name) LEFT JOIN pg_roles AS r ON r.rolname = e.name
    UNION ALL
    SELECT 2, 'membership of dbe_owner in dbe_reader',
           CASE WHEN EXISTS (SELECT FROM pg_auth_members AS a JOIN pg_roles AS m ON m.oid = a.member
                              JOIN pg_roles AS g ON g.oid = a.roleid
                             WHERE m.rolname = 'dbe_owner' AND g.rolname = 'dbe_reader') THEN 'keep' ELSE 'grant' END
    UNION ALL
    SELECT 3, 'database ' || e.name,
           CASE WHEN d.oid IS NULL THEN format('create, mark %L, revoke PUBLIC privileges', e.purpose)
                WHEN NOT EXISTS (SELECT FROM pg_db_role_setting AS s CROSS JOIN LATERAL unnest(s.setconfig) AS cfg
                                  WHERE s.setdatabase = d.oid AND starts_with(cfg, 'olist_dbe.purpose='))
                THEN format('adopt (verified): mark %L, revoke PUBLIC privileges', e.purpose)
                ELSE format('keep (verified, marked %L), revoke PUBLIC privileges', e.purpose) END
      FROM (VALUES ('olist_dbe', 'main'), ('olist_dbe_test', 'test')) AS e (name, purpose)
      LEFT JOIN pg_database AS d ON d.datname = e.name
) AS plan ORDER BY n, object;

\if :dry_run
\echo 'Dry run: nothing was changed.'
\quit
\endif

BEGIN;
SELECT 'CREATE ROLE dbe_owner LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dbe_owner') \gexec
SELECT 'CREATE ROLE dbe_reader NOLOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dbe_reader') \gexec
SELECT 'GRANT dbe_reader TO dbe_owner' WHERE NOT pg_has_role('dbe_owner', 'dbe_reader', 'MEMBER') \gexec
COMMIT;

SELECT format('CREATE DATABASE %I OWNER dbe_owner TEMPLATE template0 ENCODING %L LOCALE_PROVIDER builtin BUILTIN_LOCALE %L',
              e.name, 'UTF8', 'C.UTF-8')
  FROM (VALUES ('olist_dbe'), ('olist_dbe_test')) AS e (name)
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = e.name) \gexec

REVOKE ALL ON DATABASE olist_dbe FROM PUBLIC;
REVOKE ALL ON DATABASE olist_dbe_test FROM PUBLIC;

-- Purpose markers. The package reads them from pg_db_role_setting (not from current_setting, which a
-- client could fake with PGOPTIONS) and refuses to work in a database that lacks the expected one.
ALTER DATABASE olist_dbe SET olist_dbe.purpose = 'main';
ALTER DATABASE olist_dbe_test SET olist_dbe.purpose = 'test';

\echo
\echo 'Done:'
SELECT d.datname AS database, pg_get_userbyid(d.datdba) AS owner,
       (SELECT substr(cfg, length('olist_dbe.purpose=') + 1)
          FROM pg_db_role_setting AS s CROSS JOIN LATERAL unnest(s.setconfig) AS cfg
         WHERE s.setdatabase = d.oid AND s.setrole = 0 AND starts_with(cfg, 'olist_dbe.purpose=')) AS marker,
       has_database_privilege('public', d.datname, 'CONNECT') AS public_can_connect
  FROM pg_database AS d WHERE d.datname IN ('olist_dbe', 'olist_dbe_test') ORDER BY d.datname;

-- Report only: can the project's login reach the evaluation databases? Changing that is left to their owner.
SELECT datname, has_database_privilege('dbe_owner', datname, 'CONNECT') AS dbe_owner_can_connect
  FROM pg_database
 WHERE datname IN ('olist_blind_eval_v1', 'olist_abcd40_snapshot_v1')
 ORDER BY datname;
