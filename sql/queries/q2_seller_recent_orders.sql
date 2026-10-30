-- Q2 Seller's recent orders: a seller's orders placed in the 30 days before a reference date.
--   Filter   order_items.seller_id = :seller_id; order_purchase_timestamp in [:as_of - 30 days, :as_of);
--            every order status (shown, so canceled orders are visible as such)
--   Grain    one row per order of this seller
--   Metrics  items, items_value (sum of price) and freight of this seller's items only: an order
--            can contain items from several sellers
-- The data ends in 2018, so "recent" is relative to a fixed :as_of, never to now(). The default is
-- the seller with the most orders in August 2018, the last complete month.
--
-- @param seller_id = 6560211a-19b4-7992-c366-6cc44a7e94c0
-- @param as_of = 2018-09-01
SELECT o.order_id, o.order_purchase_timestamp, o.order_status,
       count(*) AS items,
       sum(i.price) AS items_value,
       sum(i.freight_value) AS freight
  FROM core.order_items AS i
  JOIN core.orders AS o ON o.order_id = i.order_id
 WHERE i.seller_id = :'seller_id'
   AND o.order_purchase_timestamp >= :'as_of'::date - 30
   AND o.order_purchase_timestamp < :'as_of'::date
 GROUP BY o.order_id
 ORDER BY o.order_purchase_timestamp DESC, o.order_id;
