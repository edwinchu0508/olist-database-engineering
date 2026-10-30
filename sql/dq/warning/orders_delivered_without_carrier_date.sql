-- Orders with status 'delivered' but no carrier hand-over time.
SELECT order_id, order_purchase_timestamp
FROM raw.orders
WHERE order_status = 'delivered' AND order_delivered_carrier_date IS NULL
