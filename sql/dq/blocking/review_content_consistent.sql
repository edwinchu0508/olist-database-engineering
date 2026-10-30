-- Every copy of a review_id carries identical content. core.reviews stores each review once, which is
-- only lossless while this holds (it is the evidence behind the 2NF split in sql/core/01_tables.sql).
SELECT review_id, count(*) AS copies
FROM raw.order_reviews
GROUP BY review_id
HAVING count(DISTINCT jsonb_build_array(review_score, review_comment_title, review_comment_message,
                                        review_creation_date, review_answer_timestamp)) > 1
