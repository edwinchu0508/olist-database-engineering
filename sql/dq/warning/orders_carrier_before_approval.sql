-- Orders handed to the carrier before payment approval.
SELECT order_id, order_approved_at, order_delivered_carrier_date
FROM raw.orders
WHERE order_delivered_carrier_date::timestamp < order_approved_at::timestamp
