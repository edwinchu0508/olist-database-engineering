-- Reviews attached to more than one order (one row per review). Their content is identical on every
-- copy (see blocking/review_content_consistent), so averaging scores per order counts them repeatedly.
SELECT review_id, count(*) AS orders
FROM raw.order_reviews
GROUP BY review_id
HAVING count(*) > 1
