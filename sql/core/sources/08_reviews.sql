-- New version of core.reviews: each review's content once.
-- DISTINCT, not DISTINCT ON: if two copies of a review ever disagreed, both rows would survive and the
-- MERGE would fail instead of silently keeping one of them. (The blocking check
-- review_content_consistent stops such a load earlier, with the offending review_id.)
SELECT DISTINCT
       review_id::uuid                    AS review_id,
       review_score::smallint             AS review_score,
       review_comment_title,
       review_comment_message,
       review_creation_date::timestamp    AS review_creation_date,
       review_answer_timestamp::timestamp AS review_answer_timestamp
FROM raw.order_reviews
