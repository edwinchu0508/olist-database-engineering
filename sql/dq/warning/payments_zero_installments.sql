-- Payments with 0 instalments (every real payment has at least one).
SELECT order_id, payment_sequential, payment_type, payment_value
FROM raw.order_payments
WHERE payment_installments = '0'
