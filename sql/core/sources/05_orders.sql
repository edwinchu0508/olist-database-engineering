-- New version of core.orders. The estimated delivery date is always midnight in the source (blocking
-- check estimated_delivery_is_date), so it becomes a date.
SELECT order_id::uuid                                  AS order_id,
       customer_id::uuid                               AS customer_id,
       order_status,
       order_purchase_timestamp::timestamp             AS order_purchase_timestamp,
       order_approved_at::timestamp                    AS order_approved_at,
       order_delivered_carrier_date::timestamp         AS order_delivered_carrier_date,
       order_delivered_customer_date::timestamp        AS order_delivered_customer_date,
       order_estimated_delivery_date::timestamp::date  AS order_estimated_delivery_date
FROM raw.orders
