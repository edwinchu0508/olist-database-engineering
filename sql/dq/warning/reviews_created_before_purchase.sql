-- Review/order links where the review was created before the order was placed.
SELECT r.review_id, r.order_id, r.review_creation_date, o.order_purchase_timestamp
FROM raw.order_reviews AS r
JOIN raw.orders AS o USING (order_id)
WHERE r.review_creation_date::timestamp < o.order_purchase_timestamp::timestamp
