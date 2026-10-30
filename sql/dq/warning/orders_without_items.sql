-- Orders with no items (mostly 'unavailable' and 'canceled'); they vanish from any orders x items join.
SELECT o.order_id, o.order_status
FROM raw.orders AS o
WHERE NOT EXISTS (SELECT FROM raw.order_items AS i WHERE i.order_id = o.order_id)
