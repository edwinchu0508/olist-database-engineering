-- New version of core.product_categories: every category used by a product or present in the
-- translation file. A used category without a translation gets a NULL English name, not an invented one.
SELECT c.product_category_name, t.product_category_name_english
FROM (
    SELECT product_category_name FROM raw.products WHERE product_category_name IS NOT NULL
    UNION
    SELECT product_category_name FROM raw.product_category_name_translation
) AS c
LEFT JOIN raw.product_category_name_translation AS t USING (product_category_name)
