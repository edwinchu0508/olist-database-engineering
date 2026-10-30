-- New version of core.products. The two misspelled source columns get their correct names here.
SELECT product_id::uuid                     AS product_id,
       product_category_name,
       product_name_lenght::smallint        AS product_name_length,
       product_description_lenght::smallint AS product_description_length,
       product_photos_qty::smallint         AS product_photos_qty,
       product_weight_g::integer            AS product_weight_g,
       product_length_cm::smallint          AS product_length_cm,
       product_height_cm::smallint          AS product_height_cm,
       product_width_cm::smallint           AS product_width_cm
FROM raw.products
