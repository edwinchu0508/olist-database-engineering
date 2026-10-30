-- New version of core.order_items.
SELECT order_id::uuid                AS order_id,
       order_item_id::smallint       AS order_item_id,
       product_id::uuid              AS product_id,
       seller_id::uuid               AS seller_id,
       shipping_limit_date::timestamp AS shipping_limit_date,
       price::numeric(10,2)          AS price,
       freight_value::numeric(10,2)  AS freight_value
FROM raw.order_items
