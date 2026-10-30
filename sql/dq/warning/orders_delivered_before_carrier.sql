-- Orders delivered to the customer before the carrier received them.
SELECT order_id, order_delivered_carrier_date, order_delivered_customer_date
FROM raw.orders
WHERE order_delivered_customer_date::timestamp < order_delivered_carrier_date::timestamp
