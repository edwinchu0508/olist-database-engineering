-- Demo 2: who is the customer? Read-only; run with psql against the main database:
--   & "$env:OLIST_DBE_PG_BIN\psql.exe" -X -h localhost -p $env:OLIST_DBE_PORT -U dbe_owner -d olist_dbe -f scripts\demo\customer_identity.sql

\echo '1. customer_id is issued per order: as many customer_ids as orders, fewer persons'
SELECT count(*) AS orders,
       count(DISTINCT o.customer_id) AS customer_ids,
       count(DISTINCT c.customer_unique_id) AS persons
  FROM core.orders AS o
  JOIN core.customers AS c ON c.customer_id = o.customer_id;

\echo '2. Repeat buyers, counted both ways'
SELECT (SELECT count(*) FROM (SELECT customer_id FROM core.orders GROUP BY customer_id HAVING count(*) > 1) AS x)
           AS by_customer_id,
       (SELECT count(*) FROM (SELECT c.customer_unique_id
                                FROM core.orders AS o JOIN core.customers AS c ON c.customer_id = o.customer_id
                               GROUP BY c.customer_unique_id HAVING count(*) > 1) AS x)
           AS by_person;

\echo '3. Why customers stays one row per order: one person, several addresses'
SELECT count(*) FILTER (WHERE zips > 1) AS persons_with_several_zip_prefixes,
       count(*) FILTER (WHERE states > 1) AS persons_with_several_states
  FROM (SELECT customer_unique_id,
               count(DISTINCT customer_zip_code_prefix) AS zips,
               count(DISTINCT customer_state) AS states
          FROM core.customers
         GROUP BY customer_unique_id) AS p;
