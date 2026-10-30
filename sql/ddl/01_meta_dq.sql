-- Bookkeeping schemas, created (if missing) by every `olist-dbe init`. The core tables are created
-- from sql/core/ by the same command (src/olist_dbe/db.py).

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS dq;

CREATE TABLE IF NOT EXISTS meta.load_runs (
    load_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status      text        NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    data_dir    text        NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    error       text,
    CONSTRAINT load_runs_finished_iff_done CHECK ((status = 'running') = (finished_at IS NULL))
);
-- status becomes 'succeeded' in the publish transaction itself, so it is also the commit marker:
-- 'succeeded' means the new core version is committed, and nothing else does.

-- Source file manifest per load: what exactly was loaded, and whether it is the reference dataset.
CREATE TABLE IF NOT EXISTS meta.load_files (
    load_id           bigint NOT NULL REFERENCES meta.load_runs ON DELETE CASCADE,
    table_name        text   NOT NULL,
    file_name         text   NOT NULL,
    sha256            text   NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    bytes             bigint NOT NULL,
    matches_reference boolean,  -- NULL when data_manifest.json has no entry for the file
    rows_loaded       bigint,   -- NULL until the COPY of this file has committed
    PRIMARY KEY (load_id, table_name)
);

CREATE TABLE IF NOT EXISTS dq.check_results (
    load_id     bigint  NOT NULL REFERENCES meta.load_runs ON DELETE CASCADE,
    check_name  text    NOT NULL,
    severity    text    NOT NULL CHECK (severity IN ('blocking', 'warning')),
    status      text    NOT NULL CHECK (status IN ('pass', 'warn', 'fail', 'error')),
    violations  bigint,  -- NULL when the check itself errored
    sample      jsonb,   -- up to 5 violating rows, for diagnosis
    error       text,
    duration_ms integer NOT NULL,
    PRIMARY KEY (load_id, check_name)
);

-- Rows each publish inserted, updated and deleted per core table; written in the publish transaction.
CREATE TABLE IF NOT EXISTS meta.load_changes (
    load_id    bigint NOT NULL REFERENCES meta.load_runs ON DELETE CASCADE,
    table_name text   NOT NULL,
    inserted   bigint NOT NULL,
    updated    bigint NOT NULL,
    deleted    bigint NOT NULL,
    PRIMARY KEY (load_id, table_name)
);
