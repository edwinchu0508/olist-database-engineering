# Benchmarks: one factor at a time

Seven experiments on six of the [business queries](queries.md). Each compares a reference with
variants that change exactly one thing: one candidate index, or one rewrite of the SQL. A variant is
timed only after its result has been shown to equal the reference's. Every number below comes from
the [generated report](benchmarks/report.md), which holds the full tables, the
`EXPLAIN (ANALYZE, BUFFERS)` plan of every variant, and the environment; the raw timings and plans are
in [benchmarks/runs/](benchmarks/runs/). Each experiment's hypothesis was written into
[sql/bench/experiments.toml](../sql/bench/experiments.toml) before the first measurement, and the
report prints it next to the result. Several turned out wrong.

## Method

- **Instance:** a throwaway PostgreSQL 18.6 cluster on the development machine (Windows 11), created
  with `initdb` for these runs, with the default configuration: `shared_buffers` 128MB, `work_mem`
  4MB, `random_page_cost` 4, 2 parallel workers per gather, no JIT (not available in this build). No
  other client session ran, and no autovacuum worker was active, at the start or end of any run. Not
  the shared PostgreSQL 18 service.
- **Data:** the reference dataset (scale 1: 99,441 orders, 112,650 items), loaded and checked against
  `data_manifest.json`. The core tables and their key indexes, about 91 MB, fit in shared buffers, so
  every measurement is warm: in all 66 recorded plans, every page was found in shared buffers.
- **Baseline:** only the primary keys and `orders_customer_id_key` exist. The harness refuses to start
  if core has any other index, and checks after every experiment that only these remain.
- **Per variant:** create the index (its build time and size are recorded); run the query and compare
  the result's fingerprint with the reference variant's; 3 untimed warm-up runs; 20 runs timed in the
  client (execute and fetch every row); 20 `EXPLAIN (ANALYZE, TIMING OFF)` runs for the server's
  planning and execution time; one `EXPLAIN (ANALYZE, BUFFERS)`; drop the index. No statement is
  prepared, so each run is planned afresh.
- **Per run:** `VACUUM (ANALYZE)` of core first, so all variants of a run share the same statistics.
  No `ANALYZE` follows an index build: the indexes are on plain columns, so it would only resample the
  same statistics and add noise between variants.
- **Repetition:** 3 complete runs, back to back. A variant's figure is the median of the three runs'
  p50.
- **Diagnostics:** a few variants are re-run with one planner setting changed for one transaction,
  to explain a plan (for example, what the plan the planner rejected would cost). They are not
  variants and were added after a trial run, to explain plans the trial showed.

**How large is the noise?** The BRIN variant of E4 ran exactly the reference's plan. Its per-run
difference from the reference was still −16%, −1% and +7%. The same configuration measured in two
experiments (E4's B-tree variant and E5's reference) gave 12.40 and 11.53 ms. Differences below about
15–20% are therefore not established by these runs, unless the plan changed and the buffers or row
counts account for the difference.

## Results

Client p50 in ms, median of 3 runs (server-side execution time in brackets).

| Experiment | Query | Reference | Variant | Change | Index size |
|---|---|---|---|---|---:|
| E1 | Q1 one person's orders | 3.61 (3.09) | B-tree on `customers (customer_unique_id)`: 0.705 (0.20) | −80% | 2.96 MB |
| E2 | Q2 a seller's last 30 days | 29.07 (28.12) | B-tree on `order_items (seller_id)`: 6.43 (5.88) | −78%, but only −31% against the serial plan | 872 kB |
| E3 | Q3 open orders | 31.63 (30.75) | full B-tree on `orders (order_status)`: 7.86 (7.73) | −75%, about −50% against the serial plan | 696 kB |
| | | | partial B-tree, open statuses only: 8.12 (7.05) | same as the full index | 32 kB |
| E4 | Q4 one week, daily | 15.26 (16.37) | B-tree on `orders (order_purchase_timestamp)`: 12.40 (11.75) | −19% | 2.14 MB |
| | | | BRIN on the same column: 14.91 (15.47) | none: the planner never uses it | 24 kB |
| E5 | Q4 with that B-tree | 11.53 (12.61) | filter on `order_purchase_timestamp::date`: 19.41 (19.87) | +68% (regression) | |
| E6 | Q5 monthly, 20 months | 108.6 (106.9) | B-tree on `orders (order_purchase_timestamp)`: 107.3 (109.8) | none: the plan is unchanged | 2.14 MB |
| E7 | Q6 cohorts | 227.4 (235.2) | `min() OVER (PARTITION BY person)` instead of GROUP BY + self-join: 204.3 (205.8) | −10%, near the noise | |

Every variant returned the reference's result in all three runs.

## Findings

**E1: an index pays off fully when everything else is already an index lookup.** Without it, Q1
reads all 1,029 pages of customers to find the person's 17 rows. With it, the whole plan is index
lookups: 223 buffers instead of 1,232, and 0.20 ms on the server instead of 3.09. The client time
falls less (5.1×), because at 0.7 ms the round trip and the planning (0.27 ms) dominate. The index is
36.8% of the size of its table: `customer_unique_id` is nearly unique (96,096 values in 99,441 rows),
so B-tree deduplication has little to merge.

**E2 and E3: most of the 4× was a parallel plan avoided.** Both references read their tables with
parallel sequential scans. The diagnostic with parallel query off ran the same query serially in 8.58
ms (E2) and 14.81 ms (E3) on the server, against 28.12 and 30.75 ms in parallel. In the parallel
plans, the nodes below the Gather finish long before the query does (in E2, the parallel hash join
after 4.3 of 28 ms). That points to starting and coordinating the worker, which on Windows is a new
process. The parallel references also
have a long tail: p95 133.6 and 135.9 ms, against 7.6 and 10.6 ms with the indexes. The planner
considers parallel scans here because orders, items and customers are each just above the 8 MB
`min_parallel_table_scan_size`, and its cost model does not know what a worker costs on this platform.
Against the serial plan, the indexes still help, but less:
- E2: 8.58 → 5.88 ms (−31%). The seller's 2,033 items are scattered: the bitmap scan visits 1,079 of
  the 1,502 item pages. The orders table is still read in full for the 30-day filter, so buffers fall
  only from 2,928 to 2,502. The index is small (7.3% of its table) because 112,650 entries hold only
  3,095 distinct sellers, and B-tree deduplication stores a repeated key once, with a list of row
  pointers.
- E3: 14.81 → 7.05–7.73 ms (about −50%). The index scan still touches 1,341 of the 1,419 order pages,
  because the 1,729 open orders are spread over the whole table. The saving is the work per row: a
  sequential scan checks the status of 99,441 rows and discards 97,712. Customers is still read in
  full for the hash join.
- The partial index, which holds only the open statuses, gives the same plan and the same time as
  the full one (per-run p50 7.49–9.26 against 7.31–7.87 ms) at 32 kB instead of 696 kB. Its condition
  is part of its contract: the planner uses it only for queries whose filter implies the index
  predicate. If the set of open statuses changes, the index must be rebuilt, or it is silently no
  longer used.

Changing the parallel settings was not one of the factors under test (only indexes and SQL), so it
appears only as a diagnostic.

**E4: B-tree, modest; BRIN, useless on this layout.** The B-tree finds the week's 3,008 orders
exactly. Its bitmap heap scan still visits 1,245 of the 1,419 pages, the number expected if the rows
are placed at random (1,419 × (1 − e^(−3008/1419)) ≈ 1,249): the purchase timestamp's physical
correlation is −0.001. The orders part of the plan drops to about 1.2 ms. The rest is unchanged:
the hash semi-join with all 112,650 items, and their aggregation, about 10–12 ms. Hence −19% (per run
−27%, −15%, −23%).
The planner never chose the BRIN index; the plan stayed a sequential scan, and the measured
difference is noise. Forced with `enable_seqscan = off`, the BRIN bitmap is lossy on all 1,419 pages
and its recheck discards 96,433 rows: every 128-page range spans nearly the whole two years, so it
can exclude nothing. BRIN needs rows stored roughly in the order of the column, as an append-only
table filled in time order would be. Reordering this table (CLUSTER) changes its physical layout,
which is not an index or a rewrite, and was not tested.

**E5: the same predicate, written on the cast date, loses the index (+68%).** It returns the same
orders (`ts::date >= d` exactly when `ts >= d`, for a date `d`), but the condition is on an
expression, so the B-tree cannot serve it. The plan falls back to a sequential scan with two casts per
row, and is also slower than E4's reference without any index (19.41 against 15.26 ms). The planner
has no statistics for the expression and estimates 497 rows instead of 3,008. Here the misestimate
did not change the join strategy, but it can in a larger query. The published Q4 filters on the raw
timestamp for this reason. An expression index on `(order_purchase_timestamp::date)` would also
serve the rewrite; it was not tested.

**E6: an index that buys nothing.** The 20 months cover 99,092 of the 99,441 orders (99.6%). The
planner keeps the sequential scan, and the plan and time are unchanged (per run +5%, −6%, +1%).
Forcing the index makes it worse: the bitmap scan reads all 1,419 heap pages plus 273 index pages
(server 119.0 against 109.8 ms). The same 2.14 MB index that helps E4's one-week window costs space
and load-time maintenance for this report and returns nothing.

**E7: the window rewrite is somewhat faster, and spilling is not the cause.** The reference
materializes the `delivered` CTE, because it is referenced twice, groups it into 93,094 persons and
hash-joins 96,200 rows back. The rewrite reads the join once and sorts 96,478 rows by person. The
difference, −10% (per run −4%, −15%, −15%), is near the noise floor, but its direction held in every
run and in the diagnostic. Both versions spill sorts to disk at `work_mem` = 4MB (755 and 803 temp
blocks read). With 32MB nothing spills, and both get faster by a similar amount (212.3 and 182.6 ms).
Both end with the same sort of 96,200 rows for `count(DISTINCT)`. The published Q6 stays as it is: the definitions and tests are written against it, and a gain of this
size does not justify changing it. The rewrite is kept as an equivalent form (`tests/test_bench.py`
checks that it returns the same rows).

## What the evidence supports

- For a deployment serving these queries: `customers (customer_unique_id)` (E1), `order_items
  (seller_id)` (E2, cheap) and the partial open-orders index (E3, 32 kB). A B-tree on the purchase
  timestamp only if narrow windows (E4) matter: it does nothing for wide reports (E6). No BRIN on this
  layout.
- None of them is added to `core`: the benchmark baseline must stay free of secondary indexes
  (`tests/test_core_schema.py`).

## What these measurements do not cover

- **One machine, warm caches, one client.** No measurement read from disk, ran concurrently with
  other queries or with a load, or was taken on Linux. The parallel-plan overhead in E2 and E3 is a
  property of this Windows instance and may be much smaller elsewhere.
- **Scale 1 only.** The planned 10× and 50× data sets were not built. With larger tables, the balance
  between index and sequential scans, and when sorts spill, both shift.
- **Write cost.** The load maintains every index row by row in its MERGE. How much each candidate
  slows a load was not measured.
- **Not tested:** planner settings as factors (parallel query, `work_mem`), BRIN on rows stored in time
  order, an expression index on the purchase date, covering indexes.
- **Order and timing.** Variants run in a fixed order within a run. The three runs ran back to back.
  Client times include psycopg's conversion of the rows into Python objects.

## Reproduce

On an instance of your own (the harness creates and drops indexes in the main database):

```
.venv\Scripts\olist-dbe bench
.venv\Scripts\olist-dbe bench
.venv\Scripts\olist-dbe bench
.venv\Scripts\olist-dbe bench-report
```

`bench` writes a run record to `docs/benchmarks/runs/` and exits with 1 if any variant's result
differs from its reference. `--experiment E3` runs one experiment, and `--repeat` and `--warmup`
change the protocol. `bench-report` renders `docs/benchmarks/report.md` from all the records it
finds. It flags differing code fingerprints, settings or source files across runs.
