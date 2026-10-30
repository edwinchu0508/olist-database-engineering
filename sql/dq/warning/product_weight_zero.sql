-- Products whose weight is recorded as 0 g; they distort any freight-per-gram analysis.
SELECT product_id, product_category_name
FROM raw.products
WHERE product_weight_g = '0'
