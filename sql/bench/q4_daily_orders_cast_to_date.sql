-- Q4 rewritten to filter on the purchase date instead of the raw timestamp (experiment E5).
-- The same orders as sql/queries/q4_daily_orders.sql: :from and :to are dates, so for a timestamp ts,
-- ts::date >= :from exactly when ts >= :from, and ts::date < :to exactly when ts < :to. The condition
-- is on an expression, so a B-tree on order_purchase_timestamp cannot serve it.
WITH days AS (
    SELECT d::date AS day
      FROM generate_series(:'from'::timestamp, :'to'::timestamp - interval '1 day', interval '1 day') AS d
),
window_orders AS (
    SELECT o.order_id, o.order_purchase_timestamp::date AS day, o.order_status
      FROM core.orders AS o
     WHERE o.order_purchase_timestamp::date >= :'from'::date
       AND o.order_purchase_timestamp::date < :'to'::date
),
order_value AS (
    SELECT i.order_id, sum(i.price + i.freight_value) AS value
      FROM core.order_items AS i
     WHERE i.order_id IN (SELECT order_id FROM window_orders)
     GROUP BY i.order_id
)
SELECT d.day,
       count(w.order_id) AS orders,
       coalesce(sum(v.value), 0) AS gmv,
       coalesce(sum(v.value) FILTER (WHERE w.order_status = 'delivered'), 0) AS delivered_value
  FROM days AS d
  LEFT JOIN window_orders AS w ON w.day = d.day
  LEFT JOIN order_value AS v ON v.order_id = w.order_id
 GROUP BY d.day
 ORDER BY d.day;
