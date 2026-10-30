-- Q4 Daily orders and GMV in a date window (here the week of Black Friday 2017).
--   Filter   order_purchase_timestamp in [:from, :to), a half-open range on the raw timestamp
--   Grain    one row per calendar day of the window, days without orders included
--   Metrics  orders placed (any status);
--            gmv = sum of price + freight_value of their items, any status (gross, including orders
--            later canceled);
--            delivered_value = the same for orders whose status is delivered
-- Values come from the items, not from the payments: payments differ from price + freight on 303
-- orders (installment interest, vouchers), and 775 orders have no items and add 0.
--
-- @param from = 2017-11-20
-- @param to = 2017-11-27
WITH days AS (
    SELECT d::date AS day
      FROM generate_series(:'from'::timestamp, :'to'::timestamp - interval '1 day', interval '1 day') AS d
),
window_orders AS (
    SELECT o.order_id, o.order_purchase_timestamp::date AS day, o.order_status
      FROM core.orders AS o
     WHERE o.order_purchase_timestamp >= :'from'::timestamp
       AND o.order_purchase_timestamp < :'to'::timestamp
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
