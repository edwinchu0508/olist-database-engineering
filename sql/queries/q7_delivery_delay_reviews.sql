-- Q7 Delivery delay against review score.
--   Filter   orders with status delivered and a delivery date (8 delivered orders have none; the 6
--            orders with a delivery date but another status are not delivered)
--   Grain    one row per delay bucket
--   Metrics  delay_days = delivery date - estimated delivery date, both as dates;
--            buckets: on time or early (<= 0), 1-3, 4-7, 8+ days late;
--            delivered_orders, reviewed_orders (orders with at least one review);
--            avg_score = mean over reviewed orders of the order's score, which is the mean of its
--            reviews (547 orders have more than one);
--            low_score_pct = share of reviewed orders whose score is at most 2
-- The estimate has no time of day. Comparing it with the delivery timestamp would count a delivery
-- in the afternoon of the estimated day as late. Each order counts once: joining orders to reviews
-- directly would count an order once per review. A review attached to several orders (789) is that
-- buyer's verdict on each of them and counts for each order.
WITH delivered AS (
    SELECT o.order_id, o.order_delivered_customer_date::date - o.order_estimated_delivery_date AS delay_days
      FROM core.orders AS o
     WHERE o.order_status = 'delivered'
       AND o.order_delivered_customer_date IS NOT NULL
),
order_score AS (
    SELECT l.order_id, avg(r.review_score) AS score
      FROM core.order_reviews AS l
      JOIN core.reviews AS r ON r.review_id = l.review_id
     GROUP BY l.order_id
),
bucketed AS (
    SELECT CASE WHEN d.delay_days <= 0 THEN 1 WHEN d.delay_days <= 3 THEN 2 WHEN d.delay_days <= 7 THEN 3 ELSE 4 END
               AS bucket,
           s.score
      FROM delivered AS d
      LEFT JOIN order_score AS s ON s.order_id = d.order_id
)
SELECT (ARRAY['on time or early', '1-3 days late', '4-7 days late', '8+ days late'])[bucket] AS delay,
       count(*) AS delivered_orders,
       count(score) AS reviewed_orders,
       round(avg(score), 2) AS avg_score,
       round(100.0 * count(*) FILTER (WHERE score <= 2) / nullif(count(score), 0), 2) AS low_score_pct
  FROM bucketed
 GROUP BY bucket
 ORDER BY bucket;
