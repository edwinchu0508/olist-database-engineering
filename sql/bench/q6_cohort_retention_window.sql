-- Q6 rewritten with the cohort month as a window function instead of GROUP BY and a self-join
-- (experiment E7). The same result as sql/queries/q6_cohort_retention.sql: min(month) over all of a
-- person's delivered orders is the month of their first one, attached to each of their rows.
WITH delivered AS (
    SELECT c.customer_unique_id, date_trunc('month', o.order_purchase_timestamp)::date AS month
      FROM core.orders AS o
      JOIN core.customers AS c ON c.customer_id = o.customer_id
     WHERE o.order_status = 'delivered'
),
with_cohort AS (
    SELECT customer_unique_id, month, min(month) OVER (PARTITION BY customer_unique_id) AS cohort_month
      FROM delivered
),
activity AS (
    SELECT cohort_month,
           ((extract(year FROM month) - extract(year FROM cohort_month)) * 12
            + extract(month FROM month) - extract(month FROM cohort_month))::integer AS month_number,
           customer_unique_id
      FROM with_cohort
     WHERE cohort_month BETWEEN :'from_month'::date AND :'to_month'::date
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
