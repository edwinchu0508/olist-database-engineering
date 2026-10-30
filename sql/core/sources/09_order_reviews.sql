-- New version of core.order_reviews: which review belongs to which order.
SELECT order_id::uuid  AS order_id,
       review_id::uuid AS review_id
FROM raw.order_reviews
