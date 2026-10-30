-- Orders with status 'delivered' but no payment approval time.
SELECT order_id, order_purchase_timestamp
FROM raw.orders
WHERE order_status = 'delivered' AND order_approved_at IS NULL
