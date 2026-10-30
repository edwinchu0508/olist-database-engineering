-- Rows that would break a core CHECK constraint, rule by rule. Rules that real rows violate are not
-- constraints; they are warnings (sql/dq/warning). Non-negativity is already guaranteed by
-- numbers_parse. This check casts, so it errors (also blocking) if the parse checks fail.
SELECT 'order_items: price > 0' AS rule, order_id AS row_key
FROM raw.order_items WHERE price::numeric <= 0
UNION ALL
SELECT 'order_items: order_item_id >= 1', order_id
FROM raw.order_items WHERE order_item_id::int < 1
UNION ALL
SELECT 'order_payments: payment_sequential >= 1', order_id
FROM raw.order_payments WHERE payment_sequential::int < 1
UNION ALL
SELECT 'orders: approved_at >= purchase', order_id
FROM raw.orders WHERE order_approved_at::timestamp < order_purchase_timestamp::timestamp
UNION ALL
SELECT 'orders: delivered_customer_date >= purchase', order_id
FROM raw.orders WHERE order_delivered_customer_date::timestamp < order_purchase_timestamp::timestamp
UNION ALL
SELECT 'orders: estimated_delivery_date >= purchase date', order_id
FROM raw.orders WHERE order_estimated_delivery_date::timestamp::date < order_purchase_timestamp::timestamp::date
UNION ALL
SELECT 'reviews: answer >= creation', review_id
FROM raw.order_reviews WHERE review_answer_timestamp::timestamp < review_creation_date::timestamp
