-- Demo 4: experiment E3 by hand. Everything runs in one transaction that is rolled back, so the index
-- does not outlive the script. Run with psql against the main database:
--   & "$env:OLIST_DBE_PG_BIN\psql.exe" -X -h localhost -p $env:OLIST_DBE_PORT -U dbe_owner -d olist_dbe -f scripts\demo\open_orders_plans.sql
--
-- The query is sql/queries/q3_open_orders.sql with its parameter as_of = 2018-10-18. A single
-- EXPLAIN ANALYZE is one noisy measurement; 3 runs of 20 executions each are in docs/benchmarks/report.md.
\pset pager off
BEGIN;

\echo '1. Reference, key indexes only: the planner picks a parallel plan'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT o.order_id, o.order_status, o.order_purchase_timestamp,
       DATE '2018-10-18' - o.order_purchase_timestamp::date AS days_open,
       c.customer_state
  FROM core.orders AS o
  JOIN core.customers AS c ON c.customer_id = o.customer_id
 WHERE o.order_status IN ('created', 'approved', 'invoiced', 'processing', 'shipped')
 ORDER BY o.order_purchase_timestamp, o.order_id;

\echo '2. The same with parallel query off (a diagnostic, not a variant)'
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT o.order_id, o.order_status, o.order_purchase_timestamp,
       DATE '2018-10-18' - o.order_purchase_timestamp::date AS days_open,
       c.customer_state
  FROM core.orders AS o
  JOIN core.customers AS c ON c.customer_id = o.customer_id
 WHERE o.order_status IN ('created', 'approved', 'invoiced', 'processing', 'shipped')
 ORDER BY o.order_purchase_timestamp, o.order_id;
RESET max_parallel_workers_per_gather;

\echo '3. With the partial index (open statuses only)'
CREATE INDEX demo_orders_status_open ON core.orders (order_status)
 WHERE order_status IN ('created', 'approved', 'invoiced', 'processing', 'shipped');
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT o.order_id, o.order_status, o.order_purchase_timestamp,
       DATE '2018-10-18' - o.order_purchase_timestamp::date AS days_open,
       c.customer_state
  FROM core.orders AS o
  JOIN core.customers AS c ON c.customer_id = o.customer_id
 WHERE o.order_status IN ('created', 'approved', 'invoiced', 'processing', 'shipped')
 ORDER BY o.order_purchase_timestamp, o.order_id;

\echo '4. Its size, against the table'
SELECT pg_size_pretty(pg_relation_size('core.demo_orders_status_open')) AS partial_index,
       pg_size_pretty(pg_relation_size('core.orders')) AS orders_table;

ROLLBACK;
