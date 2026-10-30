-- Orders whose payments differ from the sum of item price plus freight by more than one cent. Most
-- overpayments are instalment plans, which suggests interest is included in payment_value.
WITH paid AS (
    SELECT order_id, sum(payment_value::numeric) AS paid, max(payment_installments::int) AS max_installments
    FROM raw.order_payments
    GROUP BY order_id
),
owed AS (
    SELECT order_id, sum(price::numeric + freight_value::numeric) AS owed
    FROM raw.order_items
    GROUP BY order_id
)
SELECT order_id, paid, owed, paid - owed AS difference, max_installments
FROM paid
JOIN owed USING (order_id)
WHERE abs(paid - owed) > 0.01
