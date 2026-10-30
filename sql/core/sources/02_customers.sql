-- New version of core.customers.
SELECT customer_id::uuid        AS customer_id,
       customer_unique_id::uuid AS customer_unique_id,
       customer_zip_code_prefix,
       customer_city,
       customer_state
FROM raw.customers
