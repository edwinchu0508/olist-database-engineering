-- Products without a category (their name/description/photo counts are missing too).
SELECT product_id
FROM raw.products
WHERE product_category_name IS NULL
