-- Products without weight or dimensions.
SELECT product_id
FROM raw.products
WHERE num_nulls(product_weight_g, product_length_cm, product_height_cm, product_width_cm) > 0
