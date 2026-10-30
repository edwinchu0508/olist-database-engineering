-- Every timestamp is in ISO 'YYYY-MM-DD HH:MI:SS' form and is a real point in time. The format test
-- matters: PostgreSQL would also accept other forms whose meaning depends on the DateStyle setting.
WITH ts(column_name, value) AS (
    SELECT 'orders.order_purchase_timestamp', order_purchase_timestamp FROM raw.orders
    UNION ALL SELECT 'orders.order_approved_at', order_approved_at FROM raw.orders
    UNION ALL SELECT 'orders.order_delivered_carrier_date', order_delivered_carrier_date FROM raw.orders
    UNION ALL SELECT 'orders.order_delivered_customer_date', order_delivered_customer_date FROM raw.orders
    UNION ALL SELECT 'orders.order_estimated_delivery_date', order_estimated_delivery_date FROM raw.orders
    UNION ALL SELECT 'order_items.shipping_limit_date', shipping_limit_date FROM raw.order_items
    UNION ALL SELECT 'order_reviews.review_creation_date', review_creation_date FROM raw.order_reviews
    UNION ALL SELECT 'order_reviews.review_answer_timestamp', review_answer_timestamp FROM raw.order_reviews
)
SELECT column_name, value
FROM ts
WHERE value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$'
   OR NOT pg_input_is_valid(value, 'timestamp')
