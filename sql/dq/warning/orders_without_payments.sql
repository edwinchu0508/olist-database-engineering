-- Orders with no payment record.
SELECT o.order_id, o.order_status
FROM raw.orders AS o
WHERE NOT EXISTS (SELECT FROM raw.order_payments AS p WHERE p.order_id = o.order_id)
