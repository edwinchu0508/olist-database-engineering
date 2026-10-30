-- core tables, created once by `olist-dbe init` (search_path = core). Loads change their rows with
-- MERGE and never replace the tables, so a reader's snapshot always sees one complete version.
-- Keys are in 02_keys.sql.
--
-- Column names follow the source files, except the two misspelled product columns.
-- Each CHECK below was first verified to hold on the real data (sql/dq/blocking/*); rules the data
-- does violate are recorded as DQ warnings instead of being enforced. See docs/decisions.md.
-- Identifiers are 32-hex strings in the source and are stored as uuid (16 bytes instead of 33).
-- Codes use text + CHECK rather than char(n), which pads and compares in surprising ways.

CREATE TABLE product_categories (
    product_category_name         text NOT NULL,
    product_category_name_english text  -- NULL where the translation file has no entry
);

CREATE TABLE customers (
    customer_id              uuid NOT NULL,
    customer_unique_id       uuid NOT NULL,
    customer_zip_code_prefix text NOT NULL CHECK (customer_zip_code_prefix ~ '^[0-9]{5}$'),
    customer_city            text NOT NULL,
    customer_state           text NOT NULL CHECK (customer_state ~ '^[A-Z]{2}$')
);

CREATE TABLE sellers (
    seller_id              uuid NOT NULL,
    seller_zip_code_prefix text NOT NULL CHECK (seller_zip_code_prefix ~ '^[0-9]{5}$'),
    seller_city            text NOT NULL,
    seller_state           text NOT NULL CHECK (seller_state ~ '^[A-Z]{2}$')
);

CREATE TABLE products (
    product_id                 uuid     NOT NULL,
    product_category_name      text,
    product_name_length        smallint CHECK (product_name_length >= 0),         -- source: product_name_lenght
    product_description_length smallint CHECK (product_description_length >= 0),  -- source: product_description_lenght
    product_photos_qty         smallint CHECK (product_photos_qty >= 0),
    product_weight_g           integer  CHECK (product_weight_g >= 0),
    product_length_cm          smallint CHECK (product_length_cm >= 0),
    product_height_cm          smallint CHECK (product_height_cm >= 0),
    product_width_cm           smallint CHECK (product_width_cm >= 0)
);

CREATE TABLE orders (
    order_id                      uuid      NOT NULL,
    customer_id                   uuid      NOT NULL,
    order_status                  text      NOT NULL,
    order_purchase_timestamp      timestamp NOT NULL,
    order_approved_at             timestamp,
    order_delivered_carrier_date  timestamp,
    order_delivered_customer_date timestamp,
    -- Always midnight in the source, so it is a date, not a timestamp.
    order_estimated_delivery_date date      NOT NULL,
    CONSTRAINT orders_status_known CHECK (order_status IN (
        'created', 'approved', 'invoiced', 'processing', 'shipped', 'delivered', 'canceled', 'unavailable')),
    CONSTRAINT orders_approved_after_purchase CHECK (order_approved_at >= order_purchase_timestamp),
    CONSTRAINT orders_delivered_after_purchase CHECK (order_delivered_customer_date >= order_purchase_timestamp),
    CONSTRAINT orders_estimate_after_purchase CHECK (order_estimated_delivery_date >= order_purchase_timestamp::date)
);

CREATE TABLE order_items (
    order_id            uuid          NOT NULL,
    order_item_id       smallint      NOT NULL CHECK (order_item_id >= 1),
    product_id          uuid          NOT NULL,
    seller_id           uuid          NOT NULL,
    shipping_limit_date timestamp     NOT NULL,
    price               numeric(10,2) NOT NULL CHECK (price > 0),
    freight_value       numeric(10,2) NOT NULL CHECK (freight_value >= 0)
);

CREATE TABLE order_payments (
    order_id             uuid          NOT NULL,
    payment_sequential   smallint      NOT NULL CHECK (payment_sequential >= 1),
    payment_type         text          NOT NULL CHECK (payment_type IN (
        'credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined')),
    payment_installments smallint      NOT NULL CHECK (payment_installments >= 0),
    payment_value        numeric(10,2) NOT NULL CHECK (payment_value >= 0)
);

-- The source review file repeats a review's full content on every order it is attached to. Keyed on
-- (review_id, order_id), that content depends on review_id alone: a 2NF violation. Split into the
-- review itself and a link table.
CREATE TABLE reviews (
    review_id               uuid      NOT NULL,
    review_score            smallint  NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title    text,
    review_comment_message  text,
    review_creation_date    timestamp NOT NULL,
    review_answer_timestamp timestamp NOT NULL,
    CONSTRAINT reviews_answer_after_creation CHECK (review_answer_timestamp >= review_creation_date)
);

CREATE TABLE order_reviews (
    order_id  uuid NOT NULL,
    review_id uuid NOT NULL
);

-- One row per zip prefix, derived from the ~1M-row geolocation file (see sources/10_zip_prefix_geo.sql).
-- Not a foreign-key target: some customer and seller prefixes have no geolocation at all.
CREATE TABLE zip_prefix_geo (
    zip_code_prefix text             NOT NULL CHECK (zip_code_prefix ~ '^[0-9]{5}$'),
    lat             double precision NOT NULL,
    lng             double precision NOT NULL,
    city            text             NOT NULL,
    state           text             NOT NULL CHECK (state ~ '^[A-Z]{2}$'),
    source_points   integer          NOT NULL CHECK (source_points > 0)
);
