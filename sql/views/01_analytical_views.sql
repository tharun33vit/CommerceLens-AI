-- ==============================================================================
-- CommerceLens AI — Phase 2: PostgreSQL Validated Analytical Views
-- Layer: Semantic & Reporting Layer (v_*)
-- Purpose: Controlled, validated analytical queries serving Power BI,
--          Streamlit dashboards, and evidence-grounded Copilot retrieval.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. View: v_monthly_sales_performance
-- Description: Monthly trend of GMV (item merchandise value), freight, payments,
--              delivered order count, AOV, and MoM growth rate using LAG().
-- Grain: 1 row per Calendar Year-Month
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_monthly_sales_performance AS
WITH monthly_agg AS (
    SELECT
        d.year,
        d.month,
        d.month_year,
        COUNT(DISTINCT fo.order_id)                                         AS total_orders_placed,
        COUNT(DISTINCT CASE WHEN fo.is_delivered THEN fo.order_id END)      AS delivered_orders_count,
        SUM(CASE WHEN fo.is_delivered THEN fo.total_item_merchandise_value ELSE 0 END) AS delivered_item_merchandise_value,
        SUM(CASE WHEN fo.is_delivered THEN fo.total_freight_value ELSE 0 END)          AS delivered_freight_value,
        SUM(fo.total_payment_value)                                         AS total_payment_value,
        COUNT(DISTINCT fo.customer_key)                                     AS active_customers_count
    FROM fact_orders fo
    JOIN dim_date d ON fo.purchase_date_key = d.date_key
    GROUP BY d.year, d.month, d.month_year
)
SELECT
    year,
    month,
    month_year,
    total_orders_placed,
    delivered_orders_count,
    delivered_item_merchandise_value,
    delivered_freight_value,
    total_payment_value,
    active_customers_count,
    -- Average Order Value (AOV): Delivered Merchandise Value / Distinct Delivered Orders
    ROUND(
        CASE 
            WHEN delivered_orders_count > 0 
            THEN delivered_item_merchandise_value / delivered_orders_count 
            ELSE 0 
        END, 2
    ) AS aov_delivered,
    -- Month-over-Month GMV Growth Rate using LAG()
    ROUND(
        (delivered_item_merchandise_value - LAG(delivered_item_merchandise_value) OVER (ORDER BY year, month))
        / NULLIF(LAG(delivered_item_merchandise_value) OVER (ORDER BY year, month), 0) * 100.0, 2
    ) AS mom_gmv_growth_pct
FROM monthly_agg
ORDER BY year, month;

-- ------------------------------------------------------------------------------
-- 2. View: v_category_merchandise_performance
-- Description: Performance breakdown by product category with Pareto cumulative
--              percentage, average item price, and category ranking via DENSE_RANK().
-- Grain: 1 row per Category English Name
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_category_merchandise_performance AS
WITH cat_base AS (
    SELECT
        COALESCE(dp.category_name_english, 'unclassified') AS category_name,
        COUNT(DISTINCT foi.order_id)                        AS distinct_orders_count,
        COUNT(foi.order_item_key)                           AS items_sold_count,
        SUM(foi.price)                                      AS total_item_merchandise_value,
        SUM(foi.freight_value)                              AS total_freight_value,
        ROUND(AVG(foi.price), 2)                            AS avg_item_price,
        ROUND(SUM(foi.freight_value) / NULLIF(SUM(foi.price), 0) * 100.0, 2) AS freight_to_price_ratio_pct
    FROM fact_order_items foi
    JOIN fact_orders fo ON foi.order_id = fo.order_id
    JOIN dim_products dp ON foi.product_key = dp.product_key
    WHERE fo.is_delivered = TRUE
    GROUP BY COALESCE(dp.category_name_english, 'unclassified')
),
cat_ranked AS (
    SELECT
        category_name,
        distinct_orders_count,
        items_sold_count,
        total_item_merchandise_value,
        total_freight_value,
        avg_item_price,
        freight_to_price_ratio_pct,
        DENSE_RANK() OVER (ORDER BY total_item_merchandise_value DESC) AS revenue_rank,
        SUM(total_item_merchandise_value) OVER () AS total_marketplace_gmv,
        SUM(total_item_merchandise_value) OVER (
            ORDER BY total_item_merchandise_value DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_cumulative_gmv
    FROM cat_base
)
SELECT
    revenue_rank,
    category_name,
    distinct_orders_count,
    items_sold_count,
    total_item_merchandise_value,
    total_freight_value,
    avg_item_price,
    freight_to_price_ratio_pct,
    ROUND((running_cumulative_gmv / total_marketplace_gmv) * 100.0, 2) AS cumulative_gmv_pct
FROM cat_ranked
ORDER BY revenue_rank;

-- ------------------------------------------------------------------------------
-- 3. View: v_delivery_sla_operations
-- Description: Operational fulfillment KPIs, on-time compliance, transit duration,
--              and separate accounting of the 8 delivered orders missing timestamps.
-- Grain: Aggregate marketplace level
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_delivery_sla_operations AS
SELECT
    COUNT(order_id)                                                     AS total_orders,
    COUNT(CASE WHEN is_delivered THEN 1 END)                            AS delivered_orders_total,
    -- Strictly eligible for SLA compliance (excludes the 8 missing timestamps)
    COUNT(CASE WHEN is_eligible_for_sla THEN 1 END)                     AS sla_eligible_delivered_orders,
    -- The 8 delivered orders with missing customer delivery date reported separately
    COUNT(CASE WHEN is_delivered AND order_delivered_customer_date IS NULL THEN 1 END) AS delivered_missing_timestamp_orders,
    COUNT(CASE WHEN is_eligible_for_sla AND is_late = FALSE THEN 1 END) AS on_time_orders_count,
    COUNT(CASE WHEN is_eligible_for_sla AND is_late = TRUE THEN 1 END)  AS late_orders_count,
    -- On-Time Delivery Rate (OTDR) %
    ROUND(
        COUNT(CASE WHEN is_eligible_for_sla AND is_late = FALSE THEN 1 END)::NUMERIC
        / NULLIF(COUNT(CASE WHEN is_eligible_for_sla THEN 1 END), 0) * 100.0, 2
    ) AS on_time_delivery_rate_pct,
    -- Late Delivery Rate (LDR) %
    ROUND(
        COUNT(CASE WHEN is_eligible_for_sla AND is_late = TRUE THEN 1 END)::NUMERIC
        / NULLIF(COUNT(CASE WHEN is_eligible_for_sla THEN 1 END), 0) * 100.0, 2
    ) AS late_delivery_rate_pct,
    -- Averages across eligible deliveries
    ROUND(AVG(delivery_lead_time_days), 2)                              AS avg_delivery_lead_time_days,
    ROUND(AVG(carrier_transit_days), 2)                                 AS avg_carrier_transit_days,
    ROUND(AVG(seller_dispatch_days), 2)                                 AS avg_seller_dispatch_days,
    ROUND(AVG(sla_variance_days), 2)                                    AS avg_sla_variance_buffer_days
FROM fact_orders;

-- ------------------------------------------------------------------------------
-- 4. View: v_customer_repurchase_rfm
-- Description: Persistent customer behavioral metrics aggregated by customer_unique_id
--              (distinguishing transient checkout tokens from unique consumers).
-- Grain: 1 row per customer_unique_id
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_customer_repurchase_rfm AS
SELECT
    dc.customer_unique_id,
    COUNT(DISTINCT fo.order_id)                                         AS total_orders_placed,
    COUNT(DISTINCT CASE WHEN fo.is_delivered THEN fo.order_id END)      AS delivered_orders_count,
    SUM(CASE WHEN fo.is_delivered THEN fo.total_item_merchandise_value ELSE 0 END) AS total_customer_ltd_gmv,
    MIN(fo.order_purchase_timestamp)                                    AS first_order_timestamp,
    MAX(fo.order_purchase_timestamp)                                    AS most_recent_order_timestamp,
    ROUND(
        EXTRACT(EPOCH FROM (MAX(fo.order_purchase_timestamp) - MIN(fo.order_purchase_timestamp))) / 86400.0, 1
    ) AS customer_relationship_span_days,
    CASE WHEN COUNT(DISTINCT fo.order_id) >= 2 THEN TRUE ELSE FALSE END AS is_repeat_buyer
FROM fact_orders fo
JOIN dim_customers dc ON fo.customer_key = dc.customer_key
GROUP BY dc.customer_unique_id;

-- ------------------------------------------------------------------------------
-- 5. View: v_csat_and_delivery_correlation
-- Description: Customer satisfaction (CSAT) ratings correlated with delivery status.
-- Grain: 1 row per Delivery SLA Status (On-Time vs Late vs Other)
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_csat_and_delivery_correlation AS
SELECT
    CASE 
        WHEN fo.is_eligible_for_sla AND fo.is_late = FALSE THEN 'On-Time Delivery'
        WHEN fo.is_eligible_for_sla AND fo.is_late = TRUE  THEN 'Late Delivery'
        WHEN fo.is_delivered = FALSE                       THEN 'Non-Delivered / In-Transit'
        ELSE 'Delivered (Missing Milestone)'
    END AS fulfillment_category,
    COUNT(fr.review_key)                                                AS reviews_count,
    ROUND(AVG(fr.review_score), 2)                                      AS avg_review_score,
    COUNT(CASE WHEN fr.review_score IN (1, 2) THEN 1 END)               AS negative_reviews_count,
    ROUND(
        COUNT(CASE WHEN fr.review_score IN (1, 2) THEN 1 END)::NUMERIC
        / NULLIF(COUNT(fr.review_key), 0) * 100.0, 2
    ) AS negative_review_pct,
    COUNT(CASE WHEN fr.review_score = 5 THEN 1 END)                     AS five_star_reviews_count,
    ROUND(
        COUNT(CASE WHEN fr.review_score = 5 THEN 1 END)::NUMERIC
        / NULLIF(COUNT(fr.review_key), 0) * 100.0, 2
    ) AS five_star_pct
FROM fact_reviews fr
JOIN fact_orders fo ON fr.order_id = fo.order_id
GROUP BY 
    CASE 
        WHEN fo.is_eligible_for_sla AND fo.is_late = FALSE THEN 'On-Time Delivery'
        WHEN fo.is_eligible_for_sla AND fo.is_late = TRUE  THEN 'Late Delivery'
        WHEN fo.is_delivered = FALSE                       THEN 'Non-Delivered / In-Transit'
        ELSE 'Delivered (Missing Milestone)'
    END;

-- ------------------------------------------------------------------------------
-- 6. View: v_reconciliation_audit
-- Description: Audit view proving that pre-aggregated fact_orders totals exactly
--              reconcile with fact_order_items and fact_payments sums without fan-out.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reconciliation_audit AS
SELECT
    'fact_orders total_item_merchandise_value sum' AS metric_description,
    SUM(total_item_merchandise_value)              AS reported_value
FROM fact_orders
UNION ALL
SELECT
    'fact_order_items price sum',
    SUM(price)
FROM fact_order_items
UNION ALL
SELECT
    'fact_orders total_freight_value sum',
    SUM(total_freight_value)
FROM fact_orders
UNION ALL
SELECT
    'fact_order_items freight_value sum',
    SUM(freight_value)
FROM fact_order_items
UNION ALL
SELECT
    'fact_orders total_payment_value sum',
    SUM(total_payment_value)
FROM fact_orders
UNION ALL
SELECT
    'fact_payments payment_value sum',
    SUM(payment_value)
FROM fact_payments;
