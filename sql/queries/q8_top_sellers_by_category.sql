-- Q8 Top sellers per product category by delivered revenue.
--   Filter   delivered orders purchased in [:from, :to)
--   Grain    one row per (category, seller) among the top :top_n sellers of each category
--   Metrics  revenue = sum of price of the seller's items in the category (freight excluded: it pays
--            for shipping, not for the goods); orders (distinct), items;
--            rank = rank() by revenue within the category (equal revenue, equal rank);
--            category_share_pct = the seller's revenue / the category's revenue in %
-- Category is the English name, else the Portuguese one (2 categories lack a translation), else
-- '(no category)' for the 610 products without one.
--
-- @param from = 2017-01-01
-- @param to = 2018-09-01
-- @param top_n = 3
WITH sales AS (
    SELECT coalesce(pc.product_category_name_english, p.product_category_name, '(no category)') AS category,
           i.seller_id, i.order_id, i.price
      FROM core.order_items AS i
      JOIN core.orders AS o ON o.order_id = i.order_id
      JOIN core.products AS p ON p.product_id = i.product_id
      LEFT JOIN core.product_categories AS pc ON pc.product_category_name = p.product_category_name
     WHERE o.order_status = 'delivered'
       AND o.order_purchase_timestamp >= :'from'::timestamp
       AND o.order_purchase_timestamp < :'to'::timestamp
),
per_seller AS (
    SELECT category, seller_id, count(DISTINCT order_id) AS orders, count(*) AS items, sum(price) AS revenue
      FROM sales
     GROUP BY category, seller_id
),
ranked AS (
    SELECT s.*,
           rank() OVER (PARTITION BY category ORDER BY revenue DESC) AS rank,
           round(100 * revenue / sum(revenue) OVER (PARTITION BY category), 2) AS category_share_pct
      FROM per_seller AS s
)
SELECT r.category, r.rank, r.seller_id, s.seller_state, r.orders, r.items, r.revenue, r.category_share_pct
  FROM ranked AS r
  JOIN core.sellers AS s ON s.seller_id = r.seller_id
 WHERE r.rank <= :'top_n'::integer
 ORDER BY r.category, r.rank, r.seller_id;
