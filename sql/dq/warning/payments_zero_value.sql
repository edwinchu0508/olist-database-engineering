-- Payments with a value of 0.
SELECT order_id, payment_sequential, payment_type
FROM raw.order_payments
WHERE payment_value::numeric = 0
