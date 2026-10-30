# Design decisions

Each decision states the evidence it rests on. Counts come from the reference files pinned in
`data_manifest.json`. They were measured twice: once independently with pandas during the data
assessment, and once by the SQL checks in `sql/dq/` (see [data_quality_report.md](data_quality_report.md)).
The test suite asserts that both agree.

## Environment and isolation

- **Own database and roles.** `olist_dbe` (and `olist_dbe_test` for pytest) are owned by `dbe_owner`.
  `dbe_reader` is a no-login role with SELECT on `core`. Nothing in this project connects to the
  evaluation databases `olist_blind_eval_v1` and `olist_abcd40_snapshot_v1`. `olist-dbe check` reports
  whether the login *could* reach them, and changing that is left to their owner.
- **The bootstrap verifies before it changes anything** (`sql/bootstrap/bootstrap.sql`, run by
  `olist-dbe bootstrap`). The role and database names are generic and the server may be shared, so an
  object of the same name need not be this project's. The first version created what was missing and
  then revoked privileges and set purpose markers on whatever databases had those names, and pytest
  drops and rebuilds `core` in any database marked `test`. Now:
  - The command takes the port and the administration database explicitly. It runs psql without
    psqlrc and with every `PG*` variable except `PGPASSFILE` removed from its environment, and the
    script checks that the session reached that port and database as a superuser. The
    administration database cannot be a project or evaluation database.
  - Before the first change, the script checks every existing role and database of these names and
    refuses, with the full list of problems, if anything differs:
    - roles: attributes, memberships, role settings, and anything a project role owns or is granted
      outside the two project databases (`pg_shdepend`);
    - databases: owner, encoding and collation, settings, the marker, and the contents. Any schema,
      object in `public`, function, type, extension or other object that the project does not
      create is refused, as is any object in its schemas owned by another role.
  - An existing database without a marker is marked only if the operator names it with `--adopt`,
    after reading the dry run (`--dry-run`, in a read-only session), which lists what each database
    holds. `--adopt` never overrides a failed check.
  - It never alters an existing role or its password, and it changes no other database.
  - `tests/test_bootstrap.py` runs it on a throwaway cluster of its own (initdb). It covers 15 kinds
    of mismatch, the session checks, the removal of `PG*` variables, adoption, and that a re-run
    changes nothing. Each refusal leaves the cluster exactly as it was.
- **Builtin `C.UTF-8` collation** (PostgreSQL 17+). Text sort order is then codepoint order on every
  platform. Without it, `ORDER BY` on text, table checksums and benchmark result hashes would differ
  between a Windows workstation (where the default locale here is `Chinese (Simplified)_China.936`)
  and a Linux CI runner.
- **No password anywhere in the repository.** libpq reads it from `pgpass.conf`. `.env` holds only
  `OLIST_DBE_*` names; the package refuses a `.env` that contains `PGPASSWORD` or any other `PG*`
  variable.
- **Every connection is verified before it is used** (`src/olist_dbe/db.py`). A database name proves
  nothing: `olist_dbe_test` could be any database, and `PG*` variables left over in a terminal can
  redirect a connection. So:
  - Connection settings come from project-specific variables (`OLIST_DBE_*`) and are passed to libpq
    explicitly, so `PGHOST`, `PGPORT`, `PGDATABASE` and `PGUSER` cannot override them. The package
    refuses to run while `PGHOSTADDR`, `PGSERVICE` or `PGOPTIONS` is set, because those still change
    an explicit connection (`PGOPTIONS` can switch the role with `-c role=...`, for instance).
  - After connecting, it checks what the server reports: endpoint, `current_database()`,
    `session_user` and `current_user`, that the role is not a superuser, and the purpose marker
    `olist_dbe.purpose` (`main` or `test`) that `sql/bootstrap/bootstrap.sql` sets with
    `ALTER DATABASE ... SET`. The marker is read from `pg_db_role_setting`, so a client cannot fake
    it with `-c olist_dbe.purpose=...` (tested).
  - Any mismatch closes the connection before a single statement has written anything.
    `olist-dbe check [--test]` shows the verification.
  - pytest connects only to the database marked `test`. Its name must also end in `_test`, as a
    second, weaker guard.

## Load pipeline

**Layers:** `raw` (all text) → DQ checks → one publish transaction that MERGEs the new version into the
fixed `core` tables.

- **Every load is a full comparison.** The source is a static snapshot. Each load stages all files and
  compares the complete new version with `core`; only rows that differ are written.
  `meta.load_changes` records per table how many rows were inserted, updated and deleted. The first
  load inserts every row, a reload of the same files changes none, and a load in which one category
  translation differs updates exactly one row (all three tested).
- **Text-only, UNLOGGED staging.** COPY then never rejects a row for its type. Type problems become
  named check results with a count and sample rows, instead of an aborted COPY that reports only the
  first bad line. Staging is reproducible from the files, so it does not need WAL.
- **The recorded hash is the hash of the loaded bytes.** Each file is hashed and its header read in one
  pass; the SHA-256 is recorded in `meta.load_files` and compared with `data_manifest.json`. COPY
  hashes the bytes it actually sends, and if they differ from the recorded hash (the file changed in
  between), the staging transaction rolls back and nothing is checked or published. The test rewrites
  a file between the two reads.
- **Publish into fixed tables, in one transaction.** The `core` tables are created once by
  `olist-dbe init` and never replaced. The publish transaction runs one generated MERGE per table
  (`olist-dbe publish-sql` prints them): it inserts new keys, updates rows whose other columns differ,
  deletes keys that are gone, and leaves unchanged rows alone. The same transaction records
  `load_changes` and marks the load `succeeded`. As a result:
  - Readers are never blocked: MERGE takes ROW EXCLUSIVE locks, readers ACCESS SHARE.
  - A snapshot taken before the commit keeps seeing the complete previous version, even in a
    REPEATABLE READ transaction that first reads `core` after the commit. A snapshot taken after it
    sees only the new version. The test holds two such readers open across a load, one that had
    already read `core` and one that had not, and compares their table checksums with the previous
    version.
  - Foreign keys are `DEFERRABLE INITIALLY IMMEDIATE`, and so is the one unique key that is not a
    primary key, `orders.customer_id`. The publish transaction defers them, so the MERGEs can insert,
    update and delete in any order, and the complete new version is checked once, at commit. Every
    other statement is checked immediately.
    - Why the unique key: PostgreSQL checks an immediate unique key row by row. Two orders that
      exchange their `customer_id` make a valid new version, yet the MERGE failed halfway with a
      duplicate-key error (reproduced on 18.6; now a test).
    - Primary keys stay immediate. Each MERGE matches on the primary key, so a key never collides
      with itself, and foreign keys can only reference an immediate key.
    - The cost: the planner does not use a deferrable unique index to prove uniqueness. On 18.6, a
      `LEFT JOIN` whose columns are not used is removed from the plan when the join column has an
      immediate unique key, and kept when the key is deferrable. No foreign key references
      `orders.customer_id`, and a deferrable key could not be referenced.
  - The publish waits at most 30 s for a table lock (`lock_timeout`) and then fails with `core`
    unchanged, instead of queueing every reader behind it.
  - After the commit, `VACUUM (ANALYZE)` refreshes statistics and the visibility map for the
    benchmarks.
- **Why not a schema swap.** The first version built `core_next` and renamed it to `core` in a short
  transaction. A two-connection test reproduced its flaw on PostgreSQL 18.6: a REPEATABLE READ
  transaction whose snapshot predated the swap, and which first read `core` after it, saw 0 rows in
  `core.orders` instead of 99,441. Name lookup uses the current catalog, so it found the new tables,
  but its old snapshot could not see their rows: DDL that replaces tables is not MVCC-safe for such
  readers. The fixed-table design passes the same test. What it costs:
  - Indexes are maintained row by row during the MERGE instead of being built once over loaded data.
  - Updated and deleted rows leave dead versions until vacuum.
  - A first load into empty tables takes about 25 s on the development machine; a reload of unchanged
    files writes no core rows.
- **The publish outcome is separate from cleanup.** The status row is updated inside the publish
  transaction, so `succeeded` is the commit marker, and nothing else is.
  - `run_load()` returns: the new version is committed. Failures after the commit (VACUUM, releasing
    the lock) are reported as cleanup errors (`warning: after the commit: ...` from the CLI), never
    as a failed load.
  - If the connection breaks during the publish, the loader asks the server over a new connection.
    `succeeded` proves the commit. Otherwise it waits until the old session is gone (`pid` and
    `backend_start` in `pg_stat_activity`), because until then the server may still commit; once the
    session is gone, `running` means rolled back.
  - If neither can be established within 5 s (server unreachable, the old session still alive, or the
    status read waiting for a lock), the outcome is reported as unknown: `PublishOutcomeUnknown`,
    CLI exit status 3, distinct from a failure (exit status 1).
  - The deadline bounds every step, not only the connection attempts. Before each statement of the
    confirming session, including its target verification, `statement_timeout` is set to the time
    that is left, and that also ends a wait for a lock. The test locks `meta.load_runs` from another
    session: the answer is "unknown" after the 1 s timeout, where the first version waited for as
    long as the lock was held. Only a connection attempt pending at the deadline can overrun it, by
    up to 2 s per address, because libpq's `connect_timeout` is in whole seconds and at least 2.
- **One loader at a time.** A session-level advisory lock serialises loads. Holding the lock proves
  no other loader is alive (a lost session keeps the lock until the server ends it), so the loader
  marks any leftover `running` row as abandoned.
- **Failure handling, all tested** (`tests/test_load.py`, `tests/test_target.py`,
  `tests/test_bootstrap.py`):

  | Failure | Where it stops | Reported as | `core` |
  |---|---|---|---|
  | Bootstrap finds a role or database of the same name that differs | Before any change | refusal listing every difference | untouched |
  | Wrong endpoint, database, role or purpose marker | Before any statement | configuration error | untouched |
  | Missing file | Before any database work | failure | unchanged |
  | Header mismatch | Before staging | failure | unchanged |
  | File changed after it was hashed | Staging rolled back | failure | unchanged |
  | Blocking DQ violation | Before the publish | failure | unchanged |
  | Fault inside the publish transaction | Rolled back | failure | unchanged |
  | Two rows exchange a unique value (`orders.customer_id`) | Checked at the commit | success | new version |
  | Connection lost before the commit | Rolled back, confirmed over a new connection | failure | unchanged |
  | Connection lost after the commit | Confirmed over a new connection | success, with cleanup errors | new version |
  | Commit outcome cannot be established (server unreachable, session alive, status read blocked) | At the 5 s deadline | unknown (exit status 3) | previous or new version |
  | Concurrent load | Before a run is recorded | failure | unchanged |

## Data quality: blocking vs warning, and why no row-level quarantine

- **Blocking** checks are the preconditions of the publish: identifier format, required values,
  key uniqueness, foreign keys, parseable timestamps and numbers, value domains, and the review and
  date-type facts below. One violation stops the load.
- **Warning** checks are real anomalies of the source. Rows are kept, the count and five sample rows
  are recorded per load, and analyses must account for them.
- **No row-level quarantine.** Dropping an individual bad order would orphan its items, payments and
  reviews, and publishing the rest would silently change every metric. For a static snapshot, an
  all-or-nothing load with diagnostics (`dq.check_results.sample`) is the honest choice. Quarantine
  makes sense for a continuous feed, where holding back one bad record must not stop the others.

## Constraints are enforced only where the data holds

| Rule | Violations | Decision |
|---|---:|---|
| `approved_at >= purchase` | 0 | CHECK constraint |
| `delivered_customer_date >= purchase` | 0 | CHECK constraint |
| `estimated_delivery_date >= purchase date` | 0 | CHECK constraint |
| `price > 0` | 0 | CHECK constraint |
| `review_answer >= review_creation` | 0 | CHECK constraint |
| carrier hand-over `>=` approval | 1,359 | warning |
| carrier hand-over `>=` purchase | 166 | warning |
| delivered to customer `>=` carrier hand-over | 23 | warning |
| `payments = Σ(price + freight)` per order | 303 | warning (most overpayments are instalment plans) |

Enforcing a rule the data violates would mean either rejecting real orders or editing the source.

## Types and keys

- **Identifiers as `uuid`.** Every identifier is 32 lowercase hex digits (blocking check
  `id_format`), which `uuid` accepts. It takes 16 bytes instead of 33 as text, roughly halving key
  index size. psql shows them with hyphens, and both forms are accepted as input.
- **Codes as `text` + CHECK, not `char(n)`.** `char(n)` pads with blanks and compares in surprising
  ways. Zip prefixes keep their leading zeros (24% of customers' do).
- **Money as `numeric(10,2)`**, guarded by a check that no value has more than two decimals, because
  the cast would otherwise round silently.
- **`order_estimated_delivery_date` is a `date`.** It is midnight in all 99,441 rows (blocking check
  `estimated_delivery_is_date`).
- **Timestamps are `timestamp without time zone`.** The dataset does not state a time zone, and
  attaching one would invent information.
- **Column names follow the source**, except `product_name_lenght` / `product_description_lenght`,
  which are corrected to `…_length`.
- **No secondary indexes after a load.** Only primary keys and `orders_customer_id_key` exist
  (asserted by `tests/test_core_schema.py`). Secondary indexes are the subject of the benchmark
  experiments, which need this baseline. Note that PostgreSQL does not index the referencing side of
  a foreign key automatically, so `order_items.seller_id` and similar columns start unindexed. The
  experiments, and the indexes their results support for a deployment, are in
  [benchmarks.md](benchmarks.md).

## Model

- **`customer_id` is per order; `customer_unique_id` is the person.** Every `customer_id` has exactly
  one order, enforced by `UNIQUE (orders.customer_id)` (deferrable, see the load pipeline). Repeat-purchase analysis must use
  `customer_unique_id`: 2,997 of 96,096 people (3.12%) ordered more than once, while counting by
  `customer_id` gives 0%.
- **`customers` stays one row per order.** An address entity keyed by `customer_unique_id` would be
  wrong: 250 people appear with more than one zip prefix and 39 with more than one state.
- **Reviews are split (2NF).** In the source, 789 reviews are attached to several orders, 1,603 rows
  in all. With the key `(review_id, order_id)`, the score, text and dates depend on `review_id` alone,
  which violates 2NF. All 789 groups carry identical content (blocking check
  `review_content_consistent`), so the split into `reviews` (98,410 rows) and `order_reviews`
  (99,224 links) is lossless. `tests/test_derivations.py` proves it: the two tables joined back equal
  the source file, read with Python's csv module, field by field as a multiset of 99,224 rows. If one
  copy of a shared review is given another score, the load stops at `review_content_consistent`,
  naming that review, rather than keep one of the copies.
- **`product_categories` = categories used by products ∪ categories in the translation file.** Two
  used categories have no translation (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`).
  Their English name is NULL rather than invented, so the products → categories foreign key holds.

## Geolocation

- The source has 1,000,163 rows for 19,015 zip prefixes. 261,831 rows are exact duplicates, and
  8,556 prefixes are spelled with more than one city name.
- **The unit of aggregation is the distinct record**: a distinct (prefix, lat, lng, city, state)
  combination, with coordinates compared as numbers. The 1,000,163 rows reduce to 738,332 records.
  This sets the weights:
  - An exact duplicate counts once, however often it repeats.
  - The same coordinates under two city or state spellings count as two records. Of the 738,305
    records inside the bounding box, 18,178 repeat a (prefix, lat, lng) under another spelling: there
    are 720,127 distinct coordinates.
- `core.zip_prefix_geo` keeps one row per prefix (`sql/core/sources/10_zip_prefix_geo.sql`):
  - the **median** latitude and longitude of its records (`percentile_cont(0.5)`, interpolated
    when the count is even);
  - the **most frequent** city and state among its records; `mode()` breaks ties by taking the first
    value in code-point order, so the result is deterministic;
  - `source_points`, the number of records used.

  `tests/test_derivations.py` recomputes all of this in Python from the CSV file and matches `core`
  for all 19,011 prefixes.
- **Records outside the bounding box are dropped.** The box (lat -34 to 5.3, lng -74 to -28.8)
  encloses Brazil including its Atlantic islands. A mainland-only box would have discarded prefix
  53990, Fernando de Noronha, whose records lie at longitude -32.4. 31 rows (27 distinct records) are
  outside the box (warning `geolocation_outside_bbox`). The box is only a plausibility filter: these
  are records outside the box, and where their coordinates actually point was not verified. Four
  prefixes have no record inside the box and are therefore absent; one customer lives in one of them.
- **Not a foreign-key target.** 157 customer prefixes and 7 seller prefixes never appear in the
  geolocation file. A foreign key would have to reject those customers and sellers.

## Known limitations

- The payment mismatch explanation (instalment interest) is an inference from the data (94% of
  overpaying orders use instalments), not a documented fact.
- City names are not normalised (accents, case). Analyses by city should use the state or the zip
  prefix.
- 17 seller zip prefixes appear with more than one state. The source does not say which is right,
  so all rows are kept and the check reports them.
