-- Q5 Monthly GMV with month-over-month growth.
--   Filter   purchase months :from_month to :to_month (2017-01 to 2018-08: the complete months; 2016
--            has 4, 324, 0 and 1 orders, and September and October 2018 have 16 and 4)
--   Grain    one row per calendar month of the range, months without orders included
--   Metrics  orders, gmv, delivered_value (defined as in Q4, by purchase month);
--            gmv_mom_pct and delivered_mom_pct = change against the previous calendar month in %,
--            NULL for the first month of the range or when the previous month is 0
-- The months come from generate_series, so LAG always compares adjacent calendar months; over the
-- months that happen to have orders, December 2016 would be compared with October 2016.
--
-- @param from_month = 2017-01-01
-- @param to_month = 2018-08-01
WITH months AS (
    SELECT m::date AS month
      FROM generate_series(:'from_month'::timestamp, :'to_month'::timestamp, interval '1 month') AS m
),
order_value AS (
    SELECT i.order_id, sum(i.price + i.freight_value) AS value
      FROM core.order_items AS i
     GROUP BY i.order_id
),
monthly AS (
    SELECT date_trunc('month', o.order_purchase_timestamp)::date AS month,
           count(*) AS orders,
           coalesce(sum(v.value), 0) AS gmv,
           coalesce(sum(v.value) FILTER (WHERE o.order_status = 'delivered'), 0) AS delivered_value
      FROM core.orders AS o
      LEFT JOIN order_value AS v ON v.order_id = o.order_id
     WHERE o.order_purchase_timestamp >= :'from_month'::timestamp
       AND o.order_purchase_timestamp < :'to_month'::timestamp + interval '1 month'
     GROUP BY 1
),
series AS (
    SELECT m.month,
           coalesce(x.orders, 0) AS orders,
           coalesce(x.gmv, 0) AS gmv,
           coalesce(x.delivered_value, 0) AS delivered_value
      FROM months AS m
      LEFT JOIN monthly AS x ON x.month = m.month
)
SELECT month, orders, gmv, delivered_value,
       round(100 * (gmv - lag(gmv) OVER w) / nullif(lag(gmv) OVER w, 0), 2) AS gmv_mom_pct,
       round(100 * (delivered_value - lag(delivered_value) OVER w) / nullif(lag(delivered_value) OVER w, 0), 2)
           AS delivered_mom_pct
  FROM series
WINDOW w AS (ORDER BY month)
 ORDER BY month;
