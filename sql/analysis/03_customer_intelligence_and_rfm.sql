-- ==============================================================================
-- CommerceLens AI — SQL Analytics: Customer Intelligence and Review Sentiment
-- Script: sql/analysis/03_customer_intelligence_and_rfm.sql
-- Layer: Analytical Query Suite
-- Techniques: Persistent Identity Aggregation (customer_unique_id), RFM NTILE Scoring,
--             CSAT vs Delivery Correlation, Sentiment Distribution.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Persistent Customer Identity vs Session Token Audit & Repurchase Dynamics
-- Business Definition:
--   - Olist customer_id is a single-order checkout token (99,441 rows).
--   - customer_unique_id represents the actual consumer (96,096 distinct people).
--   - Measures repeat purchasing rate and frequency distribution.
-- ------------------------------------------------------------------------------
WITH customer_order_frequencies AS (
    SELECT
        dc.customer_unique_id,
        COUNT(DISTINCT fo.order_id)                                         AS total_orders_placed,
        COUNT(DISTINCT CASE WHEN fo.is_delivered THEN fo.order_id END)      AS delivered_orders_placed,
        SUM(CASE WHEN fo.is_delivered THEN fo.total_item_merchandise_value ELSE 0 END) AS total_customer_ltd_gmv,
        MIN(fo.order_purchase_timestamp)                                    AS first_purchase_date,
        MAX(fo.order_purchase_timestamp)                                    AS last_purchase_date
    FROM fact_orders fo
    JOIN dim_customers dc ON fo.customer_key = dc.customer_key
    GROUP BY dc.customer_unique_id
),
frequency_buckets AS (
    SELECT
        CASE 
            WHEN total_orders_placed = 1 THEN '1 Order (One-Time Buyer)'
            WHEN total_orders_placed = 2 THEN '2 Orders (Repeat Buyer)'
            WHEN total_orders_placed BETWEEN 3 AND 5 THEN '3-5 Orders (Loyal Buyer)'
            ELSE '6+ Orders (Power Buyer)'
        END AS customer_loyalty_segment,
        customer_unique_id,
        total_orders_placed,
        total_customer_ltd_gmv
    FROM customer_order_frequencies
)
SELECT
    customer_loyalty_segment,
    COUNT(customer_unique_id)                                               AS customer_count,
    ROUND(
        COUNT(customer_unique_id)::NUMERIC 
        / (SELECT COUNT(*) FROM customer_order_frequencies) * 100.0, 2
    )                                                                       AS customer_share_pct,
    SUM(total_orders_placed)                                                AS total_orders_generated,
    ROUND(SUM(total_customer_ltd_gmv), 2)                                  AS segment_total_gmv,
    ROUND(AVG(total_customer_ltd_gmv), 2)                                  AS avg_ltv_per_customer
FROM frequency_buckets
GROUP BY customer_loyalty_segment
ORDER BY MIN(total_orders_placed);


-- ------------------------------------------------------------------------------
-- 2. Customer RFM Segmentation using NTILE(5)
-- Business Definition:
--   - Recency: Days from last purchase to reference dataset cutoff (2018-10-17).
--   - Frequency: Count of distinct delivered orders.
--   - Monetary: Total delivered merchandise value.
-- ------------------------------------------------------------------------------
WITH customer_rfm_raw AS (
    SELECT
        dc.customer_unique_id,
        ROUND(
            EXTRACT(EPOCH FROM ('2018-10-17 00:00:00'::TIMESTAMP - MAX(fo.order_purchase_timestamp))) / 86400.0, 0
        )                                                                   AS recency_days,
        COUNT(DISTINCT fo.order_id)                                         AS frequency_orders,
        SUM(fo.total_item_merchandise_value)                                AS monetary_value
    FROM fact_orders fo
    JOIN dim_customers dc ON fo.customer_key = dc.customer_key
    WHERE fo.is_delivered = TRUE
    GROUP BY dc.customer_unique_id
),
rfm_scores AS (
    SELECT
        customer_unique_id,
        recency_days,
        frequency_orders,
        monetary_value,
        NTILE(5) OVER (ORDER BY recency_days ASC)   AS r_score, -- Lower recency days = higher score
        NTILE(5) OVER (ORDER BY frequency_orders DESC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary_value DESC) AS m_score
    FROM customer_rfm_raw
)
SELECT
    r_score,
    m_score,
    COUNT(customer_unique_id)                                               AS customer_count,
    ROUND(AVG(recency_days), 1)                                             AS avg_recency_days,
    ROUND(AVG(monetary_value), 2)                                           AS avg_monetary_value
FROM rfm_scores
GROUP BY r_score, m_score
ORDER BY r_score DESC, m_score DESC;


-- ------------------------------------------------------------------------------
-- 3. Review Score Distribution & Fulfillment Correlation (CSAT Analysis)
-- Business Definition:
--   - Demonstrates the empirical association between late delivery and customer review scores
--     (observational correlation; not asserting strict unconfounded causality).
--   - Analyzes star rating distributions across on-time vs late orders.
-- ------------------------------------------------------------------------------
WITH order_review_enriched AS (
    SELECT
        fo.order_id,
        fr.review_score,
        CASE 
            WHEN fo.is_eligible_for_sla AND fo.is_late = FALSE THEN 'On-Time Delivery'
            WHEN fo.is_eligible_for_sla AND fo.is_late = TRUE  THEN 'Late Delivery'
            WHEN fo.is_delivered = FALSE                       THEN 'Non-Delivered / Cancelled'
            ELSE 'Delivered (Missing Milestone)'
        END AS delivery_outcome,
        fo.delivery_lead_time_days,
        fo.sla_variance_days
    FROM fact_reviews fr
    JOIN fact_orders fo ON fr.order_id = fo.order_id
)
SELECT
    delivery_outcome,
    COUNT(order_id)                                                         AS total_reviews,
    ROUND(AVG(review_score), 2)                                             AS avg_review_score,
    COUNT(CASE WHEN review_score = 1 THEN 1 END)                            AS one_star_count,
    ROUND(
        COUNT(CASE WHEN review_score = 1 THEN 1 END)::NUMERIC 
        / NULLIF(COUNT(order_id), 0) * 100.0, 2
    )                                                                       AS one_star_pct,
    COUNT(CASE WHEN review_score = 5 THEN 1 END)                            AS five_star_count,
    ROUND(
        COUNT(CASE WHEN review_score = 5 THEN 1 END)::NUMERIC 
        / NULLIF(COUNT(order_id), 0) * 100.0, 2
    )                                                                       AS five_star_pct
FROM order_review_enriched
GROUP BY delivery_outcome
ORDER BY avg_review_score DESC;
