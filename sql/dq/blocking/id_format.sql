-- Every 32-hex identifier is well formed and lowercase, so the uuid casts in sql/core/sources cannot fail
-- and text uniqueness in raw equals uuid uniqueness in core.
SELECT 'customers.customer_id' AS column_name, customer_id AS value FROM raw.customers WHERE customer_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'customers.customer_unique_id', customer_unique_id FROM raw.customers WHERE customer_unique_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'sellers.seller_id', seller_id FROM raw.sellers WHERE seller_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'products.product_id', product_id FROM raw.products WHERE product_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'orders.order_id', order_id FROM raw.orders WHERE order_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'orders.customer_id', customer_id FROM raw.orders WHERE customer_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'order_items.order_id', order_id FROM raw.order_items WHERE order_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'order_items.product_id', product_id FROM raw.order_items WHERE product_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'order_items.seller_id', seller_id FROM raw.order_items WHERE seller_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'order_payments.order_id', order_id FROM raw.order_payments WHERE order_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'order_reviews.review_id', review_id FROM raw.order_reviews WHERE review_id !~ '^[0-9a-f]{32}$'
UNION ALL
SELECT 'order_reviews.order_id', order_id FROM raw.order_reviews WHERE order_id !~ '^[0-9a-f]{32}$'
