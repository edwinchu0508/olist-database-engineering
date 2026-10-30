-- Seller zip prefixes that appear with more than one state (one row per prefix). A zip prefix belongs
-- to a single state, so at least one of those seller rows has a wrong state.
SELECT seller_zip_code_prefix, string_agg(DISTINCT seller_state, ',') AS states
FROM raw.sellers
GROUP BY seller_zip_code_prefix
HAVING count(DISTINCT seller_state) > 1
