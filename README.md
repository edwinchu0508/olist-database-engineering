# Olist e-commerce: database engineering on PostgreSQL

A reproducible PostgreSQL 18 database for the
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(9 CSV files, 1.55 M rows). The focus is engineering: a schema derived from the data's real
relationships, a load that is atomic and safe for concurrent readers, 38 data-quality checks,
business queries whose results are checked against a second implementation, and index and rewrite
experiments measured one factor at a time, including the ones that did not help.

**Status:**
- Done:
  - Phase 1: schema, load pipeline, data quality and tests, including the fixes from two code
    reviews.
  - Business queries: 8 definitions, SQL, and saved results.
  - Benchmarks: 7 experiments on 6 of those queries.
- Next: the transaction and isolation experiments, CI, and larger scale factors (see
  [limitations](#limitations)).

Three worked cases, for a quick read: [docs/interview_cases.md](docs/interview_cases.md).

## What is in place

- **Schema from evidence** ([ERD](docs/erd.md), [decisions](docs/decisions.md)):
  - Every CHECK constraint was verified on the data first; rules the data breaks are warnings.
  - Reviews are normalised to 2NF, because the source repeats one review on several orders.
  - Identifiers are stored as `uuid`, zip prefixes as text (leading zeros), and the geolocation is
    reduced to one row per zip prefix.
- **Verified targets:** before anything runs, every connection checks endpoint, database, role (never
  a superuser) and a purpose marker set by the bootstrap. Stale `PG*` variables cannot redirect it.
- **A bootstrap that refuses to guess:** it marks only the databases it creates. An existing database
  must pass every ownership and content check, and the operator must name it with `--adopt`.
  Anything else of the same name is refused before a single change, with the full list of
  differences.
- **Atomic load, safe for readers:** CSV → all-text staging → DQ checks → one transaction that MERGEs
  the new version into the fixed `core` tables.
  - Readers are never blocked, and every snapshot sees one complete version, including REPEATABLE
    READ snapshots taken before the load (the schema swap this replaced failed that test).
  - Keys are checked against the complete new version at the commit, so rows may exchange unique
    values.
  - A failure before the commit leaves `core` untouched.
  - A lost connection is resolved over a new one. If the outcome cannot be established within 5 s
    (including a status read blocked by a lock), it is reported as unknown (exit status 3).
  - Cleanup errors after a commit never count as a failed load.
  - The SHA-256 recorded for each file is computed from the bytes COPY actually loaded.
  - A reload of the same files changes no row; `meta.load_changes` records what each load changed.
  - An advisory lock keeps loads serialised.
- **Data quality** ([report](docs/data_quality_report.md)):
  - 10 blocking checks (build preconditions) and 28 warnings. The warnings are real anomalies, such
    as 1,359 orders handed to the carrier before payment approval, and 303 orders whose payments do
    not equal price + freight.
  - Each check is a standalone SQL file in `sql/dq/`.
- **Business queries** ([definitions](docs/queries.md), [results](docs/query_results/README.md)):
  - Eight queries: a customer's history, a seller's recent orders, open orders, daily and monthly
    GMV, cohort retention, delivery delay against review score, and top sellers per category.
  - Each has a short definition (metrics, filter, grain, output) and runs unchanged in psql.
  - Every result equals a second implementation in plain Python computed from the CSV files.
  - The pitfalls each definition avoids are measured and pinned:
    - joining items and payments at once overstates the amount paid by 4.3 M;
    - `BETWEEN` on a timestamp loses a whole day (391 orders);
    - counting persons by `customer_id` gives 0% retention.
- **Benchmarks** ([findings](docs/benchmarks.md), [report](docs/benchmarks/report.md)):
  - Seven experiments; each variant changes one index or one rewrite.
  - Each variant's result must equal the reference's before it is timed.
  - Each variant gets 20 timed runs in each of 3 runs, `EXPLAIN (ANALYZE, BUFFERS)`, and index sizes.
  - The hypotheses were written down before measuring. The findings include:
    - an index that saves 80%;
    - two 4× gains that are mostly an avoided parallel plan;
    - a BRIN index the data's layout makes useless;
    - an index that buys nothing;
    - a rewrite that is 68% slower.
- **Tests (113):**
  - Row counts and every DQ count are pinned to numbers measured independently with pandas.
  - The derived tables are checked against the CSV files directly: the review split round-trips
    field by field, and `zip_prefix_geo` matches a second implementation in Python.
  - Each failure mode of the load is exercised, including faults inside the publish transaction and
    connections lost just before and just after the commit.
  - Target verification refuses the wrong database, role or marker, and spoofing attempts.
  - The bootstrap runs on a throwaway cluster of its own. It is shown to refuse 15 kinds of
    mismatching role or database without changing anything.
  - Constraints reject bad changes, and the reader role cannot write.
  - The queries match their second implementation. The benchmark harness changes one factor per
    variant, refuses a differing result, and restores the key indexes.
  - `pytest --run-report PATH` records versions, server settings, the source-file check, a code
    fingerprint and each test's outcome ([latest run](docs/test_runs/)).

## Quick start

Requires PostgreSQL 17+ (builtin collation) and Python 3.11+.

On a shared server, consider running the tests and the benchmarks on a separate instance instead:
the suite rebuilds `core` in the test database, the benchmarks create and drop indexes in the main
one, and both need control over configuration, caches and other load.

1. Install the package and configure it: copy `.env.example` to `.env` and set `OLIST_DATA_DIR` (and
   `OLIST_DBE_PG_BIN` if PostgreSQL's `bin` folder is not on PATH).

   ```
   py -3.11 -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev]"
   ```

2. Create or verify the roles, databases and purpose markers, as a superuser. Look first: the dry run
   checks everything in a read-only session, lists what any existing database of these names holds,
   and shows the plan.

   ```
   .venv\Scripts\olist-dbe bootstrap --port 5432 --admin-db postgres --dry-run
   .venv\Scripts\olist-dbe bootstrap --port 5432 --admin-db postgres
   ```

   If `olist_dbe` or `olist_dbe_test` already exists without a marker (created by the first version
   of the bootstrap, for instance), the bootstrap refuses until you name it with
   `--adopt olist_dbe --adopt olist_dbe_test`. Do so only if the dry run shows it is this project's
   database and its contents may be rebuilt. The bootstrap is safe to re-run.

3. Set the `dbe_owner` password in an interactive psql session with `\password dbe_owner`. Then store
   it in pgpass. On Windows, the helper script asks for the password at a hidden prompt and writes the
   entry with correct escaping and no byte-order mark:

   ```
   powershell -ExecutionPolicy Bypass -File scripts\set_pgpass.ps1
   ```

   On Linux/macOS, add `localhost:5432:*:dbe_owner:<password>` to `~/.pgpass` (mode 0600).

4. Verify the targets, then load and test:

   ```
   .venv\Scripts\olist-dbe check
   .venv\Scripts\olist-dbe check --test
   .venv\Scripts\olist-dbe init
   .venv\Scripts\olist-dbe load
   .venv\Scripts\olist-dbe dq-report --out docs/data_quality_report.md
   .venv\Scripts\python -m pytest --run-report docs/test_runs/latest.md
   ```

   `check` must end with `verified`; every other command refuses to run otherwise. `load` exits with
   0 when the new version is committed, 1 when nothing was published, and 3 when the outcome of the
   commit could not be established (check `olist-dbe status` before loading again).

5. Run the queries and the benchmarks:

   ```
   .venv\Scripts\olist-dbe queries --out docs/query_results
   .venv\Scripts\olist-dbe bench
   .venv\Scripts\olist-dbe bench-report
   ```

   Each `bench` writes one run record to `docs/benchmarks/runs/`. The published report is built from
   three of them.

`olist-dbe manifest` prints the SHA-256 of your CSV files. The loader compares them with
`data_manifest.json`, and the tests require an exact match, because their pinned counts were
measured on those files.

## Layout

```
sql/bootstrap/   roles and databases, checked before any change (olist-dbe bootstrap, as superuser)
sql/ddl/         bookkeeping schemas: meta (load runs, file manifest, changes), raw (staging), dq (check results)
sql/core/        core tables, keys and grants (created once by init)
sql/core/sources/  one query per core table: its new version, typed, from raw (the MERGE source)
sql/dq/          blocking/ and warning/ checks, one SQL file each
sql/queries/     the eight business queries, definition and parameters in each header
sql/bench/       benchmark experiments (experiments.toml) and the SQL rewrites they compare
src/olist_dbe/   target verification, loader, DQ runner, queries, benchmark harness, report, CLI
tests/           pytest suite (runs only against the database marked 'test')
scripts/         pgpass helper, the independent pandas profile of the source files
docs/            ERD, design decisions, queries and their results, benchmarks, DQ report,
                 data assessment, test run records, interview cases
```

## Limitations

What is known not to be covered, or covered only in part:

- **Where it was run.** Every result comes from throwaway PostgreSQL 18.6 clusters on one Windows 11
  machine ([test runs](docs/test_runs/README.md)). Nothing was run on Linux or on the shared
  PostgreSQL 18 service, by design.
- **Benchmarks** ([details](docs/benchmarks.md#what-these-measurements-do-not-cover)):
  - warm caches, one client, no concurrent load;
  - scale 1 only: no 10× or 50× data sets;
  - the cost of each index to the load was not measured;
  - planner settings appear only as diagnostics, not as tested factors.
  - The parallel-plan overhead behind E2 and E3 is specific to this instance.
- **Not built yet:**
  - the transaction and isolation experiments of the plan: lost update, write skew, SERIALIZABLE
    failures, materialized view refresh;
  - CI;
  - the optional star-schema mart.
- **Query definitions:**
  - The order status is the one in the snapshot; there is no status history. Q3's age of an open
    order is measured to a fixed date.
  - GMV is price + freight from the items, not the payments, which differ on 303 orders.
  - Q8 ranks by price only.
  - These choices are stated in [docs/queries.md](docs/queries.md).
- **Load:** the 5 s bound on confirming a lost commit can be overrun by a pending connection attempt
  (up to 2 s per address, because libpq's `connect_timeout` has whole-second granularity).
- **Data:**
  - The explanation of the payment mismatches (instalment interest) is an inference.
  - City names are not normalised.
  - 17 seller zip prefixes appear with more than one state.
  - See [known limitations](docs/decisions.md#known-limitations).
