# Three cases from this project

Each case gives the situation, what was measured, the decision, how it is verified, and what it
costs. Every number is from this repository: the tests that pin it, or the
[benchmark report](benchmarks/report.md).

## 1. Data quality and modelling: who is the customer?

**Situation.** The customers file has two identifiers, `customer_id` and `customer_unique_id`. The
natural reading is that `customer_id` is the customer.

**What the data shows.**
- Every one of the 99,441 `customer_id` values has exactly one order: it is issued per order.
- The 99,441 orders belong to 96,096 `customer_unique_id` values. 2,997 of them (3.12%) ordered more
  than once. Counted by `customer_id`, the repeat rate is exactly 0.
- In the cohort query (Q6), no `customer_id` has a second delivered order, so retention would read 0%
  in every month. 1,693 persons have delivered orders in more than one month.
- The address belongs to the order, not the person: 250 persons appear with more than one zip prefix
  and 39 with more than one state.

**Options.**
1. A `persons` table keyed by `customer_unique_id`, holding the address. That would have to pick one
   of several addresses for 250 persons, which is inventing data.
2. Keep `customers` one row per order, as the source has it, make the one-to-one link explicit, and
   define the person as `customer_unique_id` in every query that counts people.

**Decision: option 2.**
- `orders.customer_id` carries a unique key, so the one-order-per-`customer_id` fact is enforced, not
  assumed.
- docs/queries.md defines the person once, and Q1 and Q6 use it.
- The pitfall is pinned by tests:
  - `test_customer_unique_id_identifies_repeat_buyers`: 0 repeat buyers by `customer_id`, 2,997 by
    person;
  - `tests/test_queries.py`: 0 against 1,693 repeat persons.

**What it cost, and what followed.**
- The unique key had to become `DEFERRABLE`. Two orders that exchange their `customer_id` are a valid
  new version, but an immediate unique key is checked row by row, so the load's MERGE failed halfway.
  This was reproduced, and is now a test.
- The price of `DEFERRABLE`: the planner cannot use the key to prove uniqueness. A `LEFT JOIN` to
  orders whose columns are unused is no longer removed from the plan (verified on 18.6). That was
  accepted, because no query relies on it.
- Lookups by person need their own index. It was the clearest benchmark result (E1): a B-tree on
  `customers (customer_unique_id)` takes Q1 from 3.09 to 0.20 ms on the server, for 2.96 MB.

**In one minute.** "The dataset issues a new customer id for every order, so repeat-buyer metrics
computed the obvious way are exactly zero. I measured that first, kept the table at its real grain
instead of inventing a person table, enforced the one-to-one fact with a key, and pinned the pitfall
in tests. The key later had to be made deferrable for the load, which costs the planner a uniqueness
proof; I verified that cost and accepted it."

## 2. Load failure protection: core is never half-new, and the outcome is never guessed

**Situation.** A load replaces the whole dataset: 9 files, 1.55 M rows, 38 data-quality checks.
Readers may be querying `core` at the same time.

**Design.** The pipeline runs in stages:
1. COPY into all-text staging tables.
2. The checks: 10 blocking, 28 warnings.
3. One publish transaction: a MERGE per table into fixed `core` tables. The same transaction marks
   the load `succeeded`, so that status row is the commit marker.

Failures injected by the tests (each stops before the publish or rolls it back; the tests that reach
the database also check that `core`'s checksums are unchanged):
- a missing file;
- a header mismatch;
- a file changed between hashing and COPY;
- a blocking violation;
- a fault inside the publish transaction;
- a connection lost before the commit;
- a concurrent load.

**The failure that changed the design.** The first version built `core_next` and renamed it over
`core` in a short transaction, the usual "atomic swap". A two-connection test broke it on PostgreSQL
18.6. A REPEATABLE READ transaction whose snapshot predated the swap, and that first read `core` after
it, saw 0 rows in `core.orders` instead of 99,441. Name lookup used the new catalog, but the old
snapshot could not see the new tables' rows. DDL that replaces tables is not MVCC-safe for such
readers. The fix was to publish into fixed tables with MERGE in one transaction. The same test now
holds two REPEATABLE READ readers open across a load, one that had read `core` and one that had not,
and both see exactly the previous version
(`test_snapshots_taken_before_a_load_keep_seeing_the_previous_version`).

**The ambiguous commit.** If the connection drops during COMMIT, the client cannot know whether the
commit happened. The loader asks over a new connection:
- `succeeded` proves the commit.
- Otherwise it waits until the old session is gone. It identifies that session by `pid` and
  `backend_start`, because until it is gone the server may still commit.
- If neither can be established within 5 s, the answer is "unknown": exit status 3, distinct from a
  failure (1). The operator checks `olist-dbe status` before loading again.

A review found that the 5 s bound covered only the connection attempts. A status read blocked by a
lock would wait as long as the lock was held. Now `statement_timeout` is set to the remaining time
before each statement of the confirming session. The test locks `meta.load_runs` from another session
and gets "unknown" within 3 s for a 1 s timeout
(`test_commit_outcome_is_unknown_in_time_when_the_confirming_query_is_blocked`).

**What it costs.**
- The MERGE maintains indexes row by row, rather than building them once over loaded data.
- Updated rows leave dead versions until vacuum.
- A first load into empty tables takes about 25 s on the development machine. A reload of unchanged
  files writes no row.

**In one minute.** "The textbook atomic swap failed a concurrency test I wrote: an old snapshot saw
empty tables. So I publish with MERGE inside one transaction, where MVCC protects every reader, and
every failure mode is a test that checks `core`'s checksums afterwards. The subtle part is a lost
connection at COMMIT. The loader confirms over a new connection, and when it cannot prove either
outcome in bounded time it says 'unknown' rather than guess."

## 3. Query optimization: the 4× that was mostly not the index

**Situation.** Q3 lists the open orders, 1,729 of 99,441 (1.7%), with the customer's state. The
textbook answer is an index on `order_status`, and a partial one for a small subset.

**Experiment (E3).** The reference has only the key indexes. Variant 2 adds a full B-tree on
`orders (order_status)`; variant 3 adds a partial B-tree on the same key, `WHERE order_status IN`
(the open statuses). Each variant:
- was checked to return the reference's exact rows before it was timed;
- ran 20 timed executions after 3 warm-ups, in each of 3 runs.

**First result.** Client p50 31.63 ms → 7.86 ms (full) and 8.12 ms (partial): 4× faster. It looked
done.

**What the plans showed.**
- The reference used parallel sequential scans. orders and customers are just above the 8 MB
  `min_parallel_table_scan_size`.
- Re-run with parallel query off (a diagnostic, not a variant), the same reference took 14.81 ms on
  the server instead of 30.75, and the parallel reference's p95 was 135.9 ms. Most of the 4× came
  from avoiding a parallel plan that is about 16 ms slower than the serial one on this Windows
  instance, most likely the cost of starting the worker process.
- Against the serial plan, the index gains about 50%. And not for the reason usually given. The
  index scan still touches 1,341 of the 1,419 order pages, because the open orders are spread over
  the table. What it saves is checking and discarding 97,712 rows.
- E2 (a seller's orders, index on `order_items (seller_id)`) showed the same pattern: −78% as
  measured, −31% against the serial plan.

**Decision.**
- The partial index: the same plan and the same time as the full one (per-run p50s overlap), at
  32 kB instead of 696 kB.
- Its predicate is part of its contract. The planner uses it only for queries whose filter implies
  it. If the set of open statuses changes, it must be rebuilt, or it is silently ignored.
- The parallel cost is reported as a property of this instance. Tuning it was outside the
  experiment's factors (indexes and SQL only).

**The negative results reported alongside.**
- A BRIN index on the purchase timestamp (E4) is never chosen. Forced, it is lossy on all 1,419
  pages, because the column's physical correlation is −0.001.
- A B-tree on the same column does nothing for the 20-month report (E6), which covers 99.6% of
  orders.
- Filtering on `timestamp::date` instead of the raw timestamp makes Q4 68% slower (E5), because the
  index can no longer serve the condition.

**In one minute.** "I don't accept a speed-up until I can say where it comes from. The index made
the query 4× faster, but the plans showed the reference was paying for a parallel plan that is
expensive on this platform. Against the serial plan, the index is worth 2×, and through less
per-row work rather than fewer pages, because the rows are scattered. I chose the partial index:
same speed, 22× smaller. I also published the cases where an index did nothing or made things
worse, with the plan that explains each one."
