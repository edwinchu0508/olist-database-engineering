-- Seller zip prefixes absent from the geolocation file (one row per prefix).
SELECT s.seller_zip_code_prefix, count(*) AS sellers
FROM raw.sellers AS s
WHERE NOT EXISTS (SELECT FROM raw.geolocation AS g
                  WHERE g.geolocation_zip_code_prefix = s.seller_zip_code_prefix)
GROUP BY s.seller_zip_code_prefix
