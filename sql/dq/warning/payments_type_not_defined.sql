-- Payments whose type is recorded as 'not_defined'.
SELECT order_id, payment_sequential, payment_value
FROM raw.order_payments
WHERE payment_type = 'not_defined'
