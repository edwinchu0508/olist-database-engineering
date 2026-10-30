-- Q1 Customer order history: every order of one person, newest first, with what was bought and paid.
--   Filter   customers.customer_unique_id = :customer_unique_id; every order status
--   Grain    one row per order
--   Metrics  items (count), items_value (sum of price), freight (sum of freight_value),
--            paid (sum of payment_value)
-- A person is customer_unique_id: customer_id is issued afresh for every order. Items and payments
-- are summed per order before they meet, because joining both child tables of an order at once
-- would repeat each item once per payment and each payment once per item.
--
-- @param customer_unique_id = 8d50f5ea-df50-201c-cdce-dfb9e2ac8455
WITH person_orders AS (
    SELECT o.order_id, o.order_purchase_timestamp, o.order_status
      FROM core.customers AS c
      JOIN core.orders AS o ON o.customer_id = c.customer_id
     WHERE c.customer_unique_id = :'customer_unique_id'
),
items AS (
    SELECT i.order_id, count(*) AS items, sum(i.price) AS items_value, sum(i.freight_value) AS freight
      FROM core.order_items AS i
     WHERE i.order_id IN (SELECT order_id FROM person_orders)
     GROUP BY i.order_id
),
payments AS (
    SELECT p.order_id, sum(p.payment_value) AS paid
      FROM core.order_payments AS p
     WHERE p.order_id IN (SELECT order_id FROM person_orders)
     GROUP BY p.order_id
)
SELECT po.order_id, po.order_purchase_timestamp, po.order_status,
       coalesce(i.items, 0) AS items,
       coalesce(i.items_value, 0) AS items_value,
       coalesce(i.freight, 0) AS freight,
       coalesce(p.paid, 0) AS paid
  FROM person_orders AS po
  LEFT JOIN items AS i ON i.order_id = po.order_id
  LEFT JOIN payments AS p ON p.order_id = po.order_id
 ORDER BY po.order_purchase_timestamp DESC, po.order_id;
