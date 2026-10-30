-- Orders not in status 'delivered' that nevertheless have a customer delivery date.
SELECT order_id, order_status, order_delivered_customer_date
FROM raw.orders
WHERE order_status <> 'delivered' AND order_delivered_customer_date IS NOT NULL
