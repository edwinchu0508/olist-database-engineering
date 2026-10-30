-- Orders handed to the carrier before they were placed.
SELECT order_id, order_purchase_timestamp, order_delivered_carrier_date
FROM raw.orders
WHERE order_delivered_carrier_date::timestamp < order_purchase_timestamp::timestamp
