-- Included by bootstrap.sql while connected to the existing project database :db. Lists what it holds
-- and sets :db_problems to every object that this project does not create (empty if there is none).
--
-- The project creates only the schemas meta, raw, dq and core, owned by dbe_owner, and tables (with
-- their indexes, identity sequences and row types) in them, also owned by dbe_owner. It creates
-- nothing in public, no functions or other types, and no extensions besides the built-in plpgsql.

SET search_path = pg_catalog, pg_temp;

\echo
\echo 'Schemas in database' :db
SELECT n.nspname AS schema, pg_get_userbyid(n.nspowner) AS owner, count(c.oid) AS relations,
       pg_size_pretty(sum(pg_total_relation_size(c.oid)) FILTER (WHERE c.relkind IN ('r', 'm'))) AS size
  FROM pg_namespace AS n LEFT JOIN pg_class AS c ON c.relnamespace = n.oid
 WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname !~ '^pg_(toast|temp_|toast_temp_)'
 GROUP BY 1, 2 ORDER BY 1;

SELECT coalesce(string_agg('  - ' || problem, E'\n'), '') AS db_problems FROM (
    SELECT format('database %I: the session reached %I on port %s instead', :'db', current_database(),
                  current_setting('port')) AS problem
     WHERE current_database() <> :'db' OR current_setting('port') <> :'expected_port'
    UNION ALL
    SELECT format('database %I: schema %I is not one this project creates', :'db', nspname)
      FROM pg_namespace
     WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'public', 'meta', 'raw', 'dq', 'core')
       AND nspname !~ '^pg_(toast|temp_|toast_temp_)'
    UNION ALL
    SELECT format('database %I: schema %I is owned by %I', :'db', nspname, pg_get_userbyid(nspowner))
      FROM pg_namespace
     WHERE nspname IN ('meta', 'raw', 'dq', 'core') AND pg_get_userbyid(nspowner) <> 'dbe_owner'
    UNION ALL
    SELECT format('database %I: %s is owned by %I', :'db', pg_describe_object('pg_class'::regclass, c.oid, 0),
                  pg_get_userbyid(c.relowner))
      FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname IN ('meta', 'raw', 'dq', 'core') AND pg_get_userbyid(c.relowner) <> 'dbe_owner'
    UNION ALL
    SELECT format('database %I: %s, but this project creates nothing in public', :'db',
                  pg_describe_object('pg_class'::regclass, c.oid, 0))
      FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
    UNION ALL
    SELECT format('database %I: %s', :'db', pg_describe_object('pg_proc'::regclass, p.oid, 0))
      FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
     WHERE n.nspname IN ('public', 'meta', 'raw', 'dq', 'core')
    UNION ALL
    SELECT format('database %I: %s', :'db', pg_describe_object('pg_type'::regclass, t.oid, 0))
      FROM pg_type AS t JOIN pg_namespace AS n ON n.oid = t.typnamespace
     WHERE n.nspname IN ('public', 'meta', 'raw', 'dq', 'core') AND t.typrelid = 0 AND t.typcategory <> 'A'
    UNION ALL
    SELECT format('database %I: extension %I', :'db', extname) FROM pg_extension WHERE extname <> 'plpgsql'
    UNION ALL
    SELECT format('database %I: event trigger %I', :'db', evtname) FROM pg_event_trigger
    UNION ALL
    SELECT format('database %I: publication %I', :'db', pubname) FROM pg_publication
    UNION ALL
    SELECT format('database %I: subscription %I', :'db', subname)
      FROM pg_subscription WHERE subdbid = (SELECT oid FROM pg_database WHERE datname = current_database())
    UNION ALL
    SELECT format('database %I: foreign server %I', :'db', srvname) FROM pg_foreign_server
) AS p \gset
