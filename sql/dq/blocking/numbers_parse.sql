-- Numeric columns hold canonical, non-negative numbers that fit their core types. Money may have at most
-- two decimals, because numeric(10,2) would otherwise round silently. Canonical integers (no leading
-- zeros) make text uniqueness in raw equal numeric uniqueness in core.
WITH money(column_name, value) AS (
    SELECT 'order_items.price', price FROM raw.order_items
    UNION ALL SELECT 'order_items.freight_value', freight_value FROM raw.order_items
    UNION ALL SELECT 'order_payments.payment_value', payment_value FROM raw.order_payments
),
smallints(column_name, value) AS (
    SELECT 'order_items.order_item_id', order_item_id FROM raw.order_items
    UNION ALL SELECT 'order_payments.payment_sequential', payment_sequential FROM raw.order_payments
    UNION ALL SELECT 'order_payments.payment_installments', payment_installments FROM raw.order_payments
    UNION ALL SELECT 'order_reviews.review_score', review_score FROM raw.order_reviews
    UNION ALL SELECT 'products.product_name_lenght', product_name_lenght FROM raw.products
    UNION ALL SELECT 'products.product_description_lenght', product_description_lenght FROM raw.products
    UNION ALL SELECT 'products.product_photos_qty', product_photos_qty FROM raw.products
    UNION ALL SELECT 'products.product_length_cm', product_length_cm FROM raw.products
    UNION ALL SELECT 'products.product_height_cm', product_height_cm FROM raw.products
    UNION ALL SELECT 'products.product_width_cm', product_width_cm FROM raw.products
),
coordinates(column_name, value) AS (
    SELECT 'geolocation.geolocation_lat', geolocation_lat FROM raw.geolocation
    UNION ALL SELECT 'geolocation.geolocation_lng', geolocation_lng FROM raw.geolocation
)
SELECT column_name, value FROM money
WHERE value !~ '^[0-9]{1,8}(\.[0-9]{1,2})?$'
UNION ALL
SELECT column_name, value FROM smallints
WHERE value !~ '^(0|[1-9][0-9]*)$' OR NOT pg_input_is_valid(value, 'smallint')
UNION ALL
SELECT 'products.product_weight_g', product_weight_g FROM raw.products
WHERE product_weight_g !~ '^(0|[1-9][0-9]*)$' OR NOT pg_input_is_valid(product_weight_g, 'integer')
UNION ALL
SELECT column_name, value FROM coordinates
WHERE NOT pg_input_is_valid(value, 'double precision')
