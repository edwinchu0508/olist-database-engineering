-- Staging layer: one all-text table per source CSV, with the columns in file order and the source's
-- own names (typos included). The loader validates each CSV header against these definitions.
--
-- All text: COPY never rejects a row for its type, so type problems surface as named DQ check
-- results (sql/dq) instead of an aborted COPY that reports only the first bad line.
-- UNLOGGED: staging is rebuilt from the CSV files on every load, so it does not need WAL.

CREATE UNLOGGED TABLE IF NOT EXISTS raw.customers (
    customer_id              text,
    customer_unique_id       text,
    customer_zip_code_prefix text,
    customer_city            text,
    customer_state           text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.geolocation (
    geolocation_zip_code_prefix text,
    geolocation_lat             text,
    geolocation_lng             text,
    geolocation_city            text,
    geolocation_state           text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.orders (
    order_id                      text,
    customer_id                   text,
    order_status                  text,
    order_purchase_timestamp      text,
    order_approved_at             text,
    order_delivered_carrier_date  text,
    order_delivered_customer_date text,
    order_estimated_delivery_date text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.order_items (
    order_id            text,
    order_item_id       text,
    product_id          text,
    seller_id           text,
    shipping_limit_date text,
    price               text,
    freight_value       text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.order_payments (
    order_id             text,
    payment_sequential   text,
    payment_type         text,
    payment_installments text,
    payment_value        text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.order_reviews (
    review_id               text,
    order_id                text,
    review_score            text,
    review_comment_title    text,
    review_comment_message  text,
    review_creation_date    text,
    review_answer_timestamp text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.products (
    product_id                 text,
    product_category_name      text,
    product_name_lenght        text,
    product_description_lenght text,
    product_photos_qty         text,
    product_weight_g           text,
    product_length_cm          text,
    product_height_cm          text,
    product_width_cm           text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.sellers (
    seller_id              text,
    seller_zip_code_prefix text,
    seller_city            text,
    seller_state           text
);

CREATE UNLOGGED TABLE IF NOT EXISTS raw.product_category_name_translation (
    product_category_name         text,
    product_category_name_english text
);
