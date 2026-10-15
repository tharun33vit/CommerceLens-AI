-- ==============================================================================
-- CommerceLens AI — Phase 2: PostgreSQL ELT Pipeline Script
-- Layer: Staging -> Dimensions & Facts
-- Purpose: Populate Kimball Star Schema from staging tables with strict grain
--          alignment, fan-out prevention, and documented translation overrides.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Populate dim_date (2016-01-01 through 2018-12-31)
-- ------------------------------------------------------------------------------
INSERT INTO dim_date (
    date_key,
    full_date,
    year,
    quarter,
    month,
    month_name,
    month_year,
    week_of_year,
    day_of_month,
    day_of_week,
    day_name,
    is_weekend
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER AS date_key,
    d::DATE AS full_date,
    EXTRACT(YEAR FROM d)::INTEGER AS year,
    EXTRACT(QUARTER FROM d)::INTEGER AS quarter,
    EXTRACT(MONTH FROM d)::INTEGER AS month,
    TO_CHAR(d, 'Month') AS month_name,
    TO_CHAR(d, 'YYYY-MM') AS month_year,
    EXTRACT(WEEK FROM d)::INTEGER AS week_of_year,
    EXTRACT(DAY FROM d)::INTEGER AS day_of_month,
    EXTRACT(ISODOW FROM d)::INTEGER AS day_of_week,
    TO_CHAR(d, 'Day') AS day_name,
    CASE WHEN EXTRACT(ISODOW FROM d) IN (6, 7) THEN TRUE ELSE FALSE END AS is_weekend
FROM GENERATE_SERIES('2016-01-01'::DATE, '2018-12-31'::DATE, '1 day'::INTERVAL) d
ON CONFLICT (date_key) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 2. Populate dim_customers
-- ------------------------------------------------------------------------------
INSERT INTO dim_customers (
    customer_id,
    customer_unique_id,
    zip_code_prefix,
    city,
    state
)
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    customer_state
FROM stg_customers
ON CONFLICT (customer_id) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 3. Populate dim_sellers
-- ------------------------------------------------------------------------------
INSERT INTO dim_sellers (
    seller_id,
    zip_code_prefix,
    city,
    state
)
SELECT
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state
FROM stg_sellers
ON CONFLICT (seller_id) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 4. Populate dim_geography
-- ------------------------------------------------------------------------------
INSERT INTO dim_geography (
    zip_code_prefix,
    latitude,
    longitude,
    state,
    city,
    sample_points_count
)
SELECT
    zip_code_prefix,
    median_lat,
    median_lng,
    state,
    city,
    sample_points_count
FROM stg_geolocation_centroids
ON CONFLICT (zip_code_prefix) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 5. Populate dim_products
-- Documented Provenance for Translation Overrides:
-- - 'pc_gamer' (3 products) -> 'pc_gamer'
-- - 'portateis_cozinha_e_preparadores_de_alimentos' (10 products) -> 'portable_kitchen_food_preparers'
-- Null categories are preserved as NULL without artificial imputation.
-- ------------------------------------------------------------------------------
INSERT INTO dim_products (
    product_id,
    category_name_portuguese,
    category_name_english,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm,
    product_photos_qty
)
SELECT
    p.product_id,
    p.product_category_name AS category_name_portuguese,
    COALESCE(
        t.product_category_name_english,
        CASE 
            WHEN p.product_category_name = 'pc_gamer' THEN 'pc_gamer'
            WHEN p.product_category_name = 'portateis_cozinha_e_preparadores_de_alimentos' 
                 THEN 'portable_kitchen_food_preparers'
            ELSE NULL
        END
    ) AS category_name_english,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    p.product_photos_qty
FROM stg_products p
LEFT JOIN stg_category_translation t ON p.product_category_name = t.product_category_name
ON CONFLICT (product_id) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 6. Populate fact_orders
-- Fan-Out Protection: Pre-aggregate items and payments before joining
-- Excludes 8 delivered orders with missing delivery dates from is_eligible_for_sla
-- ------------------------------------------------------------------------------
WITH agg_items AS (
    SELECT
        order_id,
        COUNT(order_item_id)            AS total_items_count,
        SUM(price)                      AS total_item_merchandise_value,
        SUM(freight_value)              AS total_freight_value,
        SUM(total_item_value)           AS total_order_gross_value
    FROM stg_order_items
    GROUP BY order_id
),
agg_payments AS (
    SELECT
        order_id,
        SUM(payment_value)              AS total_payment_value,
        COUNT(payment_sequential)       AS payment_slices_count
    FROM stg_order_payments
    GROUP BY order_id
)
INSERT INTO fact_orders (
    order_id,
    customer_key,
    purchase_date_key,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    is_delivered,
    is_late,
    is_eligible_for_sla,
    delivery_lead_time_days,
    carrier_transit_days,
    seller_dispatch_days,
    sla_variance_days,
    total_items_count,
    total_item_merchandise_value,
    total_freight_value,
    total_order_gross_value,
    total_payment_value,
    payment_slices_count
)
SELECT
    o.order_id,
    c.customer_key,
    TO_CHAR(o.order_purchase_timestamp, 'YYYYMMDD')::INTEGER AS purchase_date_key,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    o.is_delivered,
    o.is_late,
    -- Strictly eligible for SLA only if delivered AND delivery timestamp exists (excludes the 8 missing orders)
    (o.is_delivered AND o.order_delivered_customer_date IS NOT NULL) AS is_eligible_for_sla,
    CASE 
        WHEN o.order_delivered_customer_date IS NOT NULL AND o.is_delivered 
        THEN EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400.0
        ELSE NULL
    END AS delivery_lead_time_days,
    CASE 
        WHEN o.order_delivered_customer_date IS NOT NULL AND o.order_delivered_carrier_date IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_delivered_carrier_date)) / 86400.0
        ELSE NULL
    END AS carrier_transit_days,
    CASE 
        WHEN o.order_delivered_carrier_date IS NOT NULL AND o.order_approved_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (o.order_delivered_carrier_date - o.order_approved_at)) / 86400.0
        ELSE NULL
    END AS seller_dispatch_days,
    CASE 
        WHEN o.order_delivered_customer_date IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (o.order_estimated_delivery_date - o.order_delivered_customer_date)) / 86400.0
        ELSE NULL
    END AS sla_variance_days,
    COALESCE(i.total_items_count, 0) AS total_items_count,
    COALESCE(i.total_item_merchandise_value, 0.00) AS total_item_merchandise_value,
    COALESCE(i.total_freight_value, 0.00) AS total_freight_value,
    COALESCE(i.total_order_gross_value, 0.00) AS total_order_gross_value,
    COALESCE(p.total_payment_value, 0.00) AS total_payment_value,
    COALESCE(p.payment_slices_count, 0) AS payment_slices_count
FROM stg_orders o
JOIN dim_customers c ON o.customer_id = c.customer_id
LEFT JOIN agg_items i ON o.order_id = i.order_id
LEFT JOIN agg_payments p ON o.order_id = p.order_id
ON CONFLICT (order_id) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 7. Populate fact_order_items
-- ------------------------------------------------------------------------------
INSERT INTO fact_order_items (
    order_id,
    order_item_id,
    product_key,
    seller_key,
    shipping_limit_date,
    price,
    freight_value,
    total_item_value
)
SELECT
    oi.order_id,
    oi.order_item_id,
    dp.product_key,
    ds.seller_key,
    oi.shipping_limit_date,
    oi.price,
    oi.freight_value,
    oi.total_item_value
FROM stg_order_items oi
JOIN dim_products dp ON oi.product_id = dp.product_id
JOIN dim_sellers ds ON oi.seller_id = ds.seller_id
ON CONFLICT (order_id, order_item_id) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 8. Populate fact_payments
-- Retains all records including the 9 vouchers with payment_value = 0.00
-- ------------------------------------------------------------------------------
INSERT INTO fact_payments (
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value
)
SELECT
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value
FROM stg_order_payments
ON CONFLICT (order_id, payment_sequential) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 9. Populate fact_reviews
-- Compound PK: (review_id, order_id)
-- ------------------------------------------------------------------------------
INSERT INTO fact_reviews (
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp
)
SELECT
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp
FROM stg_order_reviews
ON CONFLICT (review_id, order_id) DO NOTHING;
