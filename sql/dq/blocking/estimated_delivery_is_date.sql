-- order_estimated_delivery_date is always midnight, so storing it as a date loses nothing.
SELECT order_id, order_estimated_delivery_date
FROM raw.orders
WHERE order_estimated_delivery_date !~ ' 00:00:00$'
