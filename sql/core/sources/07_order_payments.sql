-- New version of core.order_payments.
SELECT order_id::uuid                  AS order_id,
       payment_sequential::smallint    AS payment_sequential,
       payment_type,
       payment_installments::smallint  AS payment_installments,
       payment_value::numeric(10,2)    AS payment_value
FROM raw.order_payments
