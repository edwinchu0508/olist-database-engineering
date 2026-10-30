-- Read access for the reader role. The tables are permanent, so these grants are made once.
GRANT USAGE ON SCHEMA core TO dbe_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO dbe_reader;
