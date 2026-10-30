-- Product categories without an English name (one row per category). Kept with a NULL English name
-- rather than an invented translation.
SELECT p.product_category_name, count(*) AS products
FROM raw.products AS p
WHERE p.product_category_name IS NOT NULL
  AND NOT EXISTS (SELECT FROM raw.product_category_name_translation AS t
                  WHERE t.product_category_name = p.product_category_name)
GROUP BY p.product_category_name
