-- Coded values stay within the sets and formats that the core CHECK constraints allow.
SELECT 'orders.order_status' AS column_name, order_status AS value FROM raw.orders
WHERE order_status NOT IN ('created', 'approved', 'invoiced', 'processing', 'shipped', 'delivered', 'canceled', 'unavailable')
UNION ALL
SELECT 'order_payments.payment_type', payment_type FROM raw.order_payments
WHERE payment_type NOT IN ('credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined')
UNION ALL
SELECT 'order_reviews.review_score', review_score FROM raw.order_reviews
WHERE review_score NOT IN ('1', '2', '3', '4', '5')
UNION ALL
SELECT 'customers.customer_zip_code_prefix', customer_zip_code_prefix FROM raw.customers
WHERE customer_zip_code_prefix !~ '^[0-9]{5}$'
UNION ALL
SELECT 'sellers.seller_zip_code_prefix', seller_zip_code_prefix FROM raw.sellers
WHERE seller_zip_code_prefix !~ '^[0-9]{5}$'
UNION ALL
SELECT 'geolocation.geolocation_zip_code_prefix', geolocation_zip_code_prefix FROM raw.geolocation
WHERE geolocation_zip_code_prefix !~ '^[0-9]{5}$'
UNION ALL
SELECT 'customers.customer_state', customer_state FROM raw.customers
WHERE customer_state !~ '^[A-Z]{2}$'
UNION ALL
SELECT 'sellers.seller_state', seller_state FROM raw.sellers
WHERE seller_state !~ '^[A-Z]{2}$'
UNION ALL
SELECT 'geolocation.geolocation_state', geolocation_state FROM raw.geolocation
WHERE geolocation_state !~ '^[A-Z]{2}$'
