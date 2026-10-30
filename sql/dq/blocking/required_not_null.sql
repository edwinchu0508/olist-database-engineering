-- Columns that are NOT NULL in core have a value in every source row.
SELECT 'customers' AS table_name, customer_id AS row_key FROM raw.customers
WHERE num_nulls(customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state) > 0
UNION ALL
SELECT 'sellers', seller_id FROM raw.sellers
WHERE num_nulls(seller_id, seller_zip_code_prefix, seller_city, seller_state) > 0
UNION ALL
SELECT 'products', product_id FROM raw.products
WHERE product_id IS NULL
UNION ALL
SELECT 'orders', order_id FROM raw.orders
WHERE num_nulls(order_id, customer_id, order_status, order_purchase_timestamp, order_estimated_delivery_date) > 0
UNION ALL
SELECT 'order_items', order_id FROM raw.order_items
WHERE num_nulls(order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value) > 0
UNION ALL
SELECT 'order_payments', order_id FROM raw.order_payments
WHERE num_nulls(order_id, payment_sequential, payment_type, payment_installments, payment_value) > 0
UNION ALL
SELECT 'order_reviews', review_id FROM raw.order_reviews
WHERE num_nulls(review_id, order_id, review_score, review_creation_date, review_answer_timestamp) > 0
UNION ALL
SELECT 'product_category_name_translation', product_category_name FROM raw.product_category_name_translation
WHERE num_nulls(product_category_name, product_category_name_english) > 0
UNION ALL
SELECT 'geolocation', geolocation_zip_code_prefix FROM raw.geolocation
WHERE num_nulls(geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state) > 0
