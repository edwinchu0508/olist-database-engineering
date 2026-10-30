-- Every core key is unique in the source, including orders.customer_id (one order per customer_id).
SELECT 'customers(customer_id)' AS key_name, customer_id AS key_value
FROM raw.customers GROUP BY customer_id HAVING count(*) > 1
UNION ALL
SELECT 'sellers(seller_id)', seller_id
FROM raw.sellers GROUP BY seller_id HAVING count(*) > 1
UNION ALL
SELECT 'products(product_id)', product_id
FROM raw.products GROUP BY product_id HAVING count(*) > 1
UNION ALL
SELECT 'orders(order_id)', order_id
FROM raw.orders GROUP BY order_id HAVING count(*) > 1
UNION ALL
SELECT 'orders(customer_id)', customer_id
FROM raw.orders GROUP BY customer_id HAVING count(*) > 1
UNION ALL
SELECT 'order_items(order_id, order_item_id)', order_id || '/' || order_item_id
FROM raw.order_items GROUP BY order_id, order_item_id HAVING count(*) > 1
UNION ALL
SELECT 'order_payments(order_id, payment_sequential)', order_id || '/' || payment_sequential
FROM raw.order_payments GROUP BY order_id, payment_sequential HAVING count(*) > 1
UNION ALL
SELECT 'order_reviews(review_id, order_id)', review_id || '/' || order_id
FROM raw.order_reviews GROUP BY review_id, order_id HAVING count(*) > 1
UNION ALL
SELECT 'product_category_name_translation(product_category_name)', product_category_name
FROM raw.product_category_name_translation GROUP BY product_category_name HAVING count(*) > 1
