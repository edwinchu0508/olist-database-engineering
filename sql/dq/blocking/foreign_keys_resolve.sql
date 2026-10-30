-- Every enforced foreign key resolves in the source. products -> product_categories is not listed:
-- the category table is built from the union of both sides, so it cannot fail.
SELECT 'orders.customer_id -> customers' AS relation, o.customer_id AS value
FROM raw.orders AS o
WHERE NOT EXISTS (SELECT FROM raw.customers AS c WHERE c.customer_id = o.customer_id)
UNION ALL
SELECT 'order_items.order_id -> orders', i.order_id
FROM raw.order_items AS i
WHERE NOT EXISTS (SELECT FROM raw.orders AS o WHERE o.order_id = i.order_id)
UNION ALL
SELECT 'order_items.product_id -> products', i.product_id
FROM raw.order_items AS i
WHERE NOT EXISTS (SELECT FROM raw.products AS p WHERE p.product_id = i.product_id)
UNION ALL
SELECT 'order_items.seller_id -> sellers', i.seller_id
FROM raw.order_items AS i
WHERE NOT EXISTS (SELECT FROM raw.sellers AS s WHERE s.seller_id = i.seller_id)
UNION ALL
SELECT 'order_payments.order_id -> orders', p.order_id
FROM raw.order_payments AS p
WHERE NOT EXISTS (SELECT FROM raw.orders AS o WHERE o.order_id = p.order_id)
UNION ALL
SELECT 'order_reviews.order_id -> orders', r.order_id
FROM raw.order_reviews AS r
WHERE NOT EXISTS (SELECT FROM raw.orders AS o WHERE o.order_id = r.order_id)
