-- New version of core.sellers.
SELECT seller_id::uuid AS seller_id,
       seller_zip_code_prefix,
       seller_city,
       seller_state
FROM raw.sellers
