# Entity relationship diagram (schema `core`)

Drawn from `sql/core/01_tables.sql` and `sql/core/02_keys.sql`. Solid lines are enforced foreign
keys (deferrable, checked immediately except inside the publish transaction; so is the unique key on
`orders.customer_id`); dotted lines are join
paths that are deliberately **not** foreign keys (see [decisions.md](decisions.md#geolocation)).

```mermaid
erDiagram
    customers ||--|| orders : "places (customer_id is per order)"
    orders ||--o{ order_items : contains
    orders ||--o{ order_payments : "paid by"
    orders ||--o{ order_reviews : "reviewed in"
    reviews ||--|{ order_reviews : "attached to"
    products ||--o{ order_items : "sold as"
    sellers ||--o{ order_items : fulfils
    product_categories |o--o{ products : classifies
    zip_prefix_geo |o..o{ customers : "zip prefix (no FK)"
    zip_prefix_geo |o..o{ sellers : "zip prefix (no FK)"

    customers {
        uuid customer_id PK
        uuid customer_unique_id "the person; not unique here"
        text customer_zip_code_prefix "5 digits"
        text customer_city
        text customer_state "2 letters"
    }
    orders {
        uuid order_id PK
        uuid customer_id FK,UK
        text order_status "8 known values"
        timestamp order_purchase_timestamp
        timestamp order_approved_at ">= purchase"
        timestamp order_delivered_carrier_date
        timestamp order_delivered_customer_date ">= purchase"
        date order_estimated_delivery_date ">= purchase date"
    }
    order_items {
        uuid order_id PK,FK
        smallint order_item_id PK
        uuid product_id FK
        uuid seller_id FK
        timestamp shipping_limit_date
        numeric price "> 0"
        numeric freight_value ">= 0"
    }
    order_payments {
        uuid order_id PK,FK
        smallint payment_sequential PK
        text payment_type "5 known values"
        smallint payment_installments
        numeric payment_value
    }
    reviews {
        uuid review_id PK
        smallint review_score "1-5"
        text review_comment_title
        text review_comment_message
        timestamp review_creation_date
        timestamp review_answer_timestamp ">= creation"
    }
    order_reviews {
        uuid order_id PK,FK
        uuid review_id PK,FK
    }
    products {
        uuid product_id PK
        text product_category_name FK "nullable"
        smallint product_name_length
        smallint product_description_length
        smallint product_photos_qty
        integer product_weight_g
        smallint product_length_cm
        smallint product_height_cm
        smallint product_width_cm
    }
    product_categories {
        text product_category_name PK
        text product_category_name_english "nullable"
    }
    sellers {
        uuid seller_id PK
        text seller_zip_code_prefix
        text seller_city
        text seller_state
    }
    zip_prefix_geo {
        text zip_code_prefix PK
        float8 lat "median over distinct records"
        float8 lng "median over distinct records"
        text city "most frequent over distinct records"
        text state "most frequent over distinct records"
        integer source_points "distinct records inside the box"
    }
```

## Pipeline schemas

| Schema | Contents | Lifetime |
|---|---|---|
| `raw` | One all-text, UNLOGGED table per CSV file | Replaced on every load |
| `dq` | `check_results`: status, violation count and sample per check per load | Persistent |
| `meta` | `load_runs` (status is the commit marker), `load_files` (SHA-256 manifest per load), `load_changes` (rows inserted, updated, deleted per table per load) | Persistent |
| `core` | The published, constrained model above | Tables created once by `olist-dbe init`; each load MERGEs their rows in one transaction |
