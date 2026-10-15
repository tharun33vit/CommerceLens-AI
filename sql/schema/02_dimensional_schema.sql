-- ==============================================================================
-- CommerceLens AI — Phase 2: PostgreSQL Dimensional Model (Star Schema) DDL
-- Layer: Analytics / Dimensional Layer (dim_*, fact_*)
-- Purpose: Optimized Kimball dimensional schema for high-performance SQL analytics,
--          Power BI semantic modeling, and evidence-grounded Copilot retrieval.
-- ==============================================================================

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS fact_order_items CASCADE;
DROP TABLE IF EXISTS fact_payments CASCADE;
DROP TABLE IF EXISTS fact_reviews CASCADE;
DROP TABLE IF EXISTS fact_orders CASCADE;
DROP TABLE IF EXISTS dim_customers CASCADE;
DROP TABLE IF EXISTS dim_sellers CASCADE;
DROP TABLE IF EXISTS dim_products CASCADE;
DROP TABLE IF EXISTS dim_geography CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;

-- ==============================================================================
-- DIMENSION TABLES
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Dimension: dim_date
-- Grain: 1 row per calendar day
-- ------------------------------------------------------------------------------
CREATE TABLE dim_date (
    date_key                    INTEGER         PRIMARY KEY, -- Format: YYYYMMDD
    full_date                   DATE            NOT NULL UNIQUE,
    year                        INTEGER         NOT NULL,
    quarter                     INTEGER         NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month                       INTEGER         NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name                  VARCHAR(20)     NOT NULL,
    month_year                  VARCHAR(7)      NOT NULL, -- YYYY-MM
    week_of_year                INTEGER         NOT NULL,
    day_of_month                INTEGER         NOT NULL,
    day_of_week                 INTEGER         NOT NULL, -- 1=Monday, 7=Sunday
    day_name                    VARCHAR(20)     NOT NULL,
    is_weekend                  BOOLEAN         NOT NULL
);

-- ------------------------------------------------------------------------------
-- 2. Dimension: dim_customers
-- Grain: 1 row per customer_id (order-specific session token)
-- Attribute customer_unique_id tracks persistent repeat customers
-- ------------------------------------------------------------------------------
CREATE TABLE dim_customers (
    customer_key                SERIAL          PRIMARY KEY,
    customer_id                 VARCHAR(32)     NOT NULL UNIQUE,
    customer_unique_id          VARCHAR(32)     NOT NULL,
    zip_code_prefix             VARCHAR(5)      NOT NULL,
    city                        VARCHAR(100)    NOT NULL,
    state                       VARCHAR(2)      NOT NULL
);

-- ------------------------------------------------------------------------------
-- 3. Dimension: dim_sellers
-- Grain: 1 row per seller_id
-- ------------------------------------------------------------------------------
CREATE TABLE dim_sellers (
    seller_key                  SERIAL          PRIMARY KEY,
    seller_id                   VARCHAR(32)     NOT NULL UNIQUE,
    zip_code_prefix             VARCHAR(5)      NOT NULL,
    city                        VARCHAR(100)    NOT NULL,
    state                       VARCHAR(2)      NOT NULL
);

-- ------------------------------------------------------------------------------
-- 4. Dimension: dim_products
-- Grain: 1 row per product_id SKU
-- Note: Preserves Portuguese category while enriching English translation.
-- ------------------------------------------------------------------------------
CREATE TABLE dim_products (
    product_key                 SERIAL          PRIMARY KEY,
    product_id                  VARCHAR(32)     NOT NULL UNIQUE,
    category_name_portuguese    VARCHAR(100),
    category_name_english       VARCHAR(100),
    product_weight_g            INTEGER,
    product_length_cm           INTEGER,
    product_height_cm           INTEGER,
    product_width_cm            INTEGER,
    product_photos_qty          INTEGER
);

-- ------------------------------------------------------------------------------
-- 5. Dimension: dim_geography
-- Grain: 1 row per 5-digit zip_code_prefix (median latitude/longitude centroid)
-- Avoids 1:N fan-out joins from raw coordinates table
-- ------------------------------------------------------------------------------
CREATE TABLE dim_geography (
    geo_key                     SERIAL          PRIMARY KEY,
    zip_code_prefix             VARCHAR(5)      NOT NULL UNIQUE,
    latitude                    NUMERIC(10, 6)  NOT NULL,
    longitude                   NUMERIC(10, 6)  NOT NULL,
    state                       VARCHAR(2)      NOT NULL,
    city                        VARCHAR(100)    NOT NULL,
    sample_points_count         INTEGER         NOT NULL
);

-- ==============================================================================
-- FACT TABLES
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 6. Fact: fact_orders
-- Grain: 1 row per order_id
-- Contains order lifecycle timestamps, SLA status, and pre-aggregated commercial metrics.
-- Fan-out Protection: Items and payments are pre-aggregated before loading this table.
-- ------------------------------------------------------------------------------
CREATE TABLE fact_orders (
    order_id                        VARCHAR(32)     PRIMARY KEY,
    customer_key                    INTEGER         NOT NULL REFERENCES dim_customers(customer_key),
    purchase_date_key               INTEGER         NOT NULL REFERENCES dim_date(date_key),
    order_status                    VARCHAR(20)     NOT NULL,
    order_purchase_timestamp        TIMESTAMP       NOT NULL,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP       NOT NULL,
    is_delivered                    BOOLEAN         NOT NULL,
    is_late                         BOOLEAN         NOT NULL,
    -- Eligibility for SLA compliance: MUST be delivered AND customer delivery date IS NOT NULL.
    -- Strictly excludes the 8 delivered orders with missing delivery dates from the on-time denominator!
    is_eligible_for_sla             BOOLEAN         NOT NULL,
    delivery_lead_time_days         NUMERIC(10, 4),
    carrier_transit_days            NUMERIC(10, 4),
    seller_dispatch_days            NUMERIC(10, 4),
    sla_variance_days               NUMERIC(10, 4),
    -- Pre-aggregated item metrics (Order Grain)
    total_items_count               INTEGER         NOT NULL DEFAULT 0,
    total_item_merchandise_value    NUMERIC(12, 2)  NOT NULL DEFAULT 0.00, -- Sum of item prices (GMV)
    total_freight_value             NUMERIC(12, 2)  NOT NULL DEFAULT 0.00,
    total_order_gross_value         NUMERIC(12, 2)  NOT NULL DEFAULT 0.00, -- Merchandise + Freight
    -- Pre-aggregated payment metrics (Order Grain)
    total_payment_value             NUMERIC(12, 2)  NOT NULL DEFAULT 0.00,
    payment_slices_count            INTEGER         NOT NULL DEFAULT 0
);

-- ------------------------------------------------------------------------------
-- 7. Fact: fact_order_items
-- Grain: 1 row per (order_id, order_item_id)
-- Detailed merchandise item line fact
-- ------------------------------------------------------------------------------
CREATE TABLE fact_order_items (
    order_item_key              SERIAL          PRIMARY KEY,
    order_id                    VARCHAR(32)     NOT NULL REFERENCES fact_orders(order_id),
    order_item_id               INTEGER         NOT NULL,
    product_key                 INTEGER         NOT NULL REFERENCES dim_products(product_key),
    seller_key                  INTEGER         NOT NULL REFERENCES dim_sellers(seller_key),
    shipping_limit_date         TIMESTAMP       NOT NULL,
    price                       NUMERIC(10, 2)  NOT NULL, -- Item Merchandise Value (GMV base)
    freight_value               NUMERIC(10, 2)  NOT NULL,
    total_item_value            NUMERIC(10, 2)  NOT NULL,
    CONSTRAINT uk_fact_order_items UNIQUE (order_id, order_item_id)
);

-- ------------------------------------------------------------------------------
-- 8. Fact: fact_payments
-- Grain: 1 row per (order_id, payment_sequential)
-- Retains all payment lines including 9 zero-value vouchers
-- ------------------------------------------------------------------------------
CREATE TABLE fact_payments (
    payment_key                 SERIAL          PRIMARY KEY,
    order_id                    VARCHAR(32)     NOT NULL REFERENCES fact_orders(order_id),
    payment_sequential          INTEGER         NOT NULL,
    payment_type                VARCHAR(20)     NOT NULL,
    payment_installments        INTEGER         NOT NULL,
    payment_value               NUMERIC(10, 2)  NOT NULL,
    CONSTRAINT uk_fact_payments UNIQUE (order_id, payment_sequential)
);

-- ------------------------------------------------------------------------------
-- 9. Fact: fact_reviews
-- Grain: 1 row per compound (review_id, order_id)
-- Customer satisfaction scores and Portuguese feedback text
-- ------------------------------------------------------------------------------
CREATE TABLE fact_reviews (
    review_key                  SERIAL          PRIMARY KEY,
    review_id                   VARCHAR(32)     NOT NULL,
    order_id                    VARCHAR(32)     NOT NULL REFERENCES fact_orders(order_id),
    review_score                INTEGER         NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title        TEXT,
    review_comment_message      TEXT,
    review_creation_date        TIMESTAMP       NOT NULL,
    review_answer_timestamp     TIMESTAMP       NOT NULL,
    CONSTRAINT uk_fact_reviews UNIQUE (review_id, order_id)
);

-- ==============================================================================
-- PERFORMANCE INDEXES
-- ==============================================================================
CREATE INDEX idx_fact_orders_cust ON fact_orders(customer_key);
CREATE INDEX idx_fact_orders_date ON fact_orders(purchase_date_key);
CREATE INDEX idx_fact_orders_status ON fact_orders(order_status);
CREATE INDEX idx_fact_orders_sla ON fact_orders(is_eligible_for_sla, is_late);

CREATE INDEX idx_fact_items_order ON fact_order_items(order_id);
CREATE INDEX idx_fact_items_prod ON fact_order_items(product_key);
CREATE INDEX idx_fact_items_sell ON fact_order_items(seller_key);

CREATE INDEX idx_fact_payments_order ON fact_payments(order_id);
CREATE INDEX idx_fact_payments_type ON fact_payments(payment_type);

CREATE INDEX idx_fact_reviews_order ON fact_reviews(order_id);
CREATE INDEX idx_fact_reviews_score ON fact_reviews(review_score);

CREATE INDEX idx_dim_cust_unique ON dim_customers(customer_unique_id);
CREATE INDEX idx_dim_cust_state ON dim_customers(state);
CREATE INDEX idx_dim_sell_state ON dim_sellers(state);
CREATE INDEX idx_dim_prod_cat ON dim_products(category_name_english);
