-- Customer zip prefixes absent from the geolocation file (one row per prefix). This is why
-- core.zip_prefix_geo is not a foreign-key target.
SELECT c.customer_zip_code_prefix, count(*) AS customers
FROM raw.customers AS c
WHERE NOT EXISTS (SELECT FROM raw.geolocation AS g
                  WHERE g.geolocation_zip_code_prefix = c.customer_zip_code_prefix)
GROUP BY c.customer_zip_code_prefix
