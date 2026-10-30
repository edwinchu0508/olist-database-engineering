-- Q6 Monthly cohort retention of buyers.
--   Filter   delivered orders; cohorts :from_month to :to_month
--   Grain    one row per (cohort month, month number) with at least one active buyer
--   Metrics  cohort_month = month of the person's first delivered order;
--            month_number = calendar months from the cohort month to the order's purchase month;
--            active_customers = distinct persons with a delivered order in that month;
--            cohort_size = persons in the cohort (its month 0);
--            retention_pct = active_customers / cohort_size in %
-- A person is customer_unique_id. Counted by customer_id, which is issued per order, nobody would
-- ever come back. A person whose first delivered order is from 2016 belongs to a 2016 cohort and is
-- not counted in any 2017 cohort.
--
-- @param from_month = 2017-01-01
-- @param to_month = 2018-08-01
WITH delivered AS (
    SELECT c.customer_unique_id, date_trunc('month', o.order_purchase_timestamp)::date AS month
      FROM core.orders AS o
      JOIN core.customers AS c ON c.customer_id = o.customer_id
     WHERE o.order_status = 'delivered'
),
firsts AS (
    SELECT customer_unique_id, min(month) AS cohort_month
      FROM delivered
     GROUP BY customer_unique_id
),
activity AS (
    SELECT f.cohort_month,
           ((extract(year FROM d.month) - extract(year FROM f.cohort_month)) * 12
            + extract(month FROM d.month) - extract(month FROM f.cohort_month))::integer AS month_number,
           d.customer_unique_id
      FROM delivered AS d
      JOIN firsts AS f ON f.customer_unique_id = d.customer_unique_id
     WHERE f.cohort_month BETWEEN :'from_month'::date AND :'to_month'::date
),
counts AS (
    SELECT cohort_month, month_number, count(DISTINCT customer_unique_id) AS active_customers
      FROM activity
     GROUP BY cohort_month, month_number
)
SELECT cohort_month, month_number, active_customers,
       first_value(active_customers) OVER cohort AS cohort_size,
       round(100.0 * active_customers / first_value(active_customers) OVER cohort, 2) AS retention_pct
  FROM counts
WINDOW cohort AS (PARTITION BY cohort_month ORDER BY month_number)
 ORDER BY cohort_month, month_number;
