-- Q3 Open order backlog: orders that have not reached a final status, oldest first.
--   Filter   order_status in (created, approved, invoiced, processing, shipped); delivered,
--            canceled and unavailable are final
--   Grain    one row per open order
--   Metrics  days_open = :as_of - purchase date; the customer's state, for routing
-- The status is the one recorded in the snapshot. :as_of is the day after the last purchase in the
-- data. Open orders are 1.7% of all orders, the case for a partial index.
--
-- @param as_of = 2018-10-18
SELECT o.order_id, o.order_status, o.order_purchase_timestamp,
       :'as_of'::date - o.order_purchase_timestamp::date AS days_open,
       c.customer_state
  FROM core.orders AS o
  JOIN core.customers AS c ON c.customer_id = o.customer_id
 WHERE o.order_status IN ('created', 'approved', 'invoiced', 'processing', 'shipped')
 ORDER BY o.order_purchase_timestamp, o.order_id;
