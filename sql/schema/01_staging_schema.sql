-- ==============================================================================
-- CommerceLens AI — Phase 2: PostgreSQL Staging Schema DDL
-- Layer: Staging Layer (stg_*)
-- Purpose: Ingest cleaned Olist CSV/Parquet datasets with strict types and grain
-- ==============================================================================

-- Drop staging tables if recreating (in correct dependency order)
DROP TABLE IF EXISTS stg_order_items CASCADE;
DROP TABLE IF EXISTS stg_order_payments CASCADE;
DROP TABLE IF EXISTS stg_order_reviews CASCADE;
DROP TABLE IF EXISTS stg_orders CASCADE;
DROP TABLE IF EXISTS stg_customers CASCADE;
DROP TABLE IF EXISTS stg_sellers CASCADE;
DROP TABLE IF EXISTS stg_products CASCADE;
DROP TABLE IF EXISTS stg_category_translation CASCADE;
DROP TABLE IF EXISTS stg_geolocation_centroids CASCADE;

-- ------------------------------------------------------------------------------
-- 1. Table: stg_customers
-- Grain: 1 row per customer_id (order-specific session token)
-- ------------------------------------------------------------------------------
CREATE TABLE stg_customers (
    customer_id                 VARCHAR(32)     PRIMARY KEY,
    customer_unique_id          VARCHAR(32)     NOT NULL,
    customer_zip_code_prefix    VARCHAR(5)      NOT NULL,
    customer_city               VARCHAR(100)    NOT NULL,
    customer_state              VARCHAR(2)      NOT NULL
);

-- ------------------------------------------------------------------------------
-- 2. Table: stg_sellers
-- Grain: 1 row per seller_id
-- ------------------------------------------------------------------------------
CREATE TABLE stg_sellers (
    seller_id                   VARCHAR(32)     PRIMARY KEY,
    seller_zip_code_prefix      VARCHAR(5)      NOT NULL,
    seller_city                 VARCHAR(100)    NOT NULL,
    seller_state                VARCHAR(2)      NOT NULL
);

-- ------------------------------------------------------------------------------
-- 3. Table: stg_category_translation
-- Grain: 1 row per product_category_name
-- ------------------------------------------------------------------------------
CREATE TABLE stg_category_translation (
    product_category_name           VARCHAR(100)    PRIMARY KEY,
    product_category_name_english   VARCHAR(100)    NOT NULL
);

-- ------------------------------------------------------------------------------
-- 4. Table: stg_products
-- Grain: 1 row per product_id
-- ------------------------------------------------------------------------------
CREATE TABLE stg_products (
    product_id                      VARCHAR(32)     PRIMARY KEY,
    product_category_name           VARCHAR(100),
    product_name_lenght             INTEGER,
    product_description_lenght      INTEGER,
    product_photos_qty              INTEGER,
    product_weight_g                INTEGER,
    product_length_cm               INTEGER,
    product_height_cm               INTEGER,
    product_width_cm                INTEGER,
    product_category_name_english   VARCHAR(100)
);

-- ------------------------------------------------------------------------------
-- 5. Table: stg_geolocation_centroids
-- Grain: 1 row per 5-digit zip_code_prefix (median latitude/longitude centroid)
-- ------------------------------------------------------------------------------
CREATE TABLE stg_geolocation_centroids (
    zip_code_prefix             VARCHAR(5)      PRIMARY KEY,
    median_lat                  NUMERIC(10, 6)  NOT NULL,
    median_lng                  NUMERIC(10, 6)  NOT NULL,
    state                       VARCHAR(2)      NOT NULL,
    city                        VARCHAR(100)    NOT NULL,
    sample_points_count         INTEGER         NOT NULL
);

-- ------------------------------------------------------------------------------
-- 6. Table: stg_orders
-- Grain: 1 row per order_id
-- ------------------------------------------------------------------------------
CREATE TABLE stg_orders (
    order_id                        VARCHAR(32)     PRIMARY KEY,
    customer_id                     VARCHAR(32)     NOT NULL,
    order_status                    VARCHAR(20)     NOT NULL,
    order_purchase_timestamp        TIMESTAMP       NOT NULL,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP       NOT NULL,
    is_delivered                    BOOLEAN         NOT NULL,
    is_late                         BOOLEAN         NOT NULL,
    delivery_lead_time_days         NUMERIC(10, 4),
    has_timestamp_anomaly           BOOLEAN         NOT NULL DEFAULT FALSE
);

-- ------------------------------------------------------------------------------
-- 7. Table: stg_order_items
-- Grain: 1 row per (order_id, order_item_id)
-- ------------------------------------------------------------------------------
CREATE TABLE stg_order_items (
    order_id                    VARCHAR(32)     NOT NULL,
    order_item_id               INTEGER         NOT NULL,
    product_id                  VARCHAR(32)     NOT NULL,
    seller_id                   VARCHAR(32)     NOT NULL,
    shipping_limit_date         TIMESTAMP       NOT NULL,
    price                       NUMERIC(10, 2)  NOT NULL,
    freight_value               NUMERIC(10, 2)  NOT NULL,
    total_item_value            NUMERIC(10, 2)  NOT NULL,
    is_negative_price           BOOLEAN         NOT NULL DEFAULT FALSE,
    is_negative_freight         BOOLEAN         NOT NULL DEFAULT FALSE,
    PRIMARY KEY (order_id, order_item_id)
);

-- ------------------------------------------------------------------------------
-- 8. Table: stg_order_payments
-- Grain: 1 row per (order_id, payment_sequential)
-- Note: Retains 9 voucher records with payment_value = 0.00
-- ------------------------------------------------------------------------------
CREATE TABLE stg_order_payments (
    order_id                    VARCHAR(32)     NOT NULL,
    payment_sequential          INTEGER         NOT NULL,
    payment_type                VARCHAR(20)     NOT NULL,
    payment_installments        INTEGER         NOT NULL,
    payment_value               NUMERIC(10, 2)  NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

-- ------------------------------------------------------------------------------
-- 9. Table: stg_order_reviews
-- Grain: 1 row per compound (review_id, order_id)
-- Note: review_id alone has 789 duplicate groups; compound key is 100% unique
-- ------------------------------------------------------------------------------
CREATE TABLE stg_order_reviews (
    review_id                   VARCHAR(32)     NOT NULL,
    order_id                    VARCHAR(32)     NOT NULL,
    review_score                INTEGER         NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title        TEXT,
    review_comment_message      TEXT,
    review_creation_date        TIMESTAMP       NOT NULL,
    review_answer_timestamp     TIMESTAMP       NOT NULL,
    PRIMARY KEY (review_id, order_id)
);

-- ------------------------------------------------------------------------------
-- Indexes for Staging Performance
-- ------------------------------------------------------------------------------
CREATE INDEX idx_stg_orders_cust ON stg_orders(customer_id);
CREATE INDEX idx_stg_orders_status ON stg_orders(order_status);
CREATE INDEX idx_stg_items_order ON stg_order_items(order_id);
CREATE INDEX idx_stg_items_prod ON stg_order_items(product_id);
CREATE INDEX idx_stg_items_sell ON stg_order_items(seller_id);
CREATE INDEX idx_stg_payments_order ON stg_order_payments(order_id);
CREATE INDEX idx_stg_reviews_order ON stg_order_reviews(order_id);
