-- Orders with status 'delivered' but no customer delivery date; delivery-time metrics must exclude them.
SELECT order_id, order_purchase_timestamp
FROM raw.orders
WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL
