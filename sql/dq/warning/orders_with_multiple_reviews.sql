-- Orders with more than one review (one row per order). Joining orders to reviews fans these orders out,
-- so per-order averages must first pick or aggregate one review per order.
SELECT order_id, count(*) AS reviews
FROM raw.order_reviews
GROUP BY order_id
HAVING count(*) > 1
