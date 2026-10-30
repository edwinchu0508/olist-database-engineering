-- Orders with no review.
SELECT o.order_id, o.order_status
FROM raw.orders AS o
WHERE NOT EXISTS (SELECT FROM raw.order_reviews AS r WHERE r.order_id = o.order_id)
