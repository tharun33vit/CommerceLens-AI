-- ==============================================================================
-- CommerceLens AI — SQL Analytics: Delivery Operations and SLA Performance
-- Script: sql/analysis/02_delivery_operations_and_sla.sql
-- Layer: Analytical Query Suite
-- Techniques: Strict Denominator Isolation (Excluding 8 Missing Delivery Timestamps),
--             Corridor Analysis, Milestone Decomposition, Window Ranking (RANK, DENSE_RANK).
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Operational Fulfillment & SLA Compliance Summary
-- Strict Compliance Rule:
--   - Denominator for OTDR/LDR strictly requires is_eligible_for_sla = TRUE
--     (which enforces is_delivered = TRUE AND order_delivered_customer_date IS NOT NULL).
--   - The 8 delivered orders missing customer delivery timestamps are reported separately.
-- ------------------------------------------------------------------------------
SELECT
    COUNT(order_id)                                                         AS total_orders,
    COUNT(CASE WHEN is_delivered THEN 1 END)                                AS total_delivered_orders,
    -- Strictly SLA-eligible cohort (Denominator = 96,470 orders)
    COUNT(CASE WHEN is_eligible_for_sla THEN 1 END)                         AS sla_eligible_delivered_orders,
    -- Discrepancy cohort: Delivered but missing customer delivery timestamp (Numerator = 8)
    COUNT(CASE WHEN is_delivered AND order_delivered_customer_date IS NULL THEN 1 END) AS delivered_missing_timestamp_orders,
    -- Non-delivered orders missing delivery timestamp (2,957 orders: 2,950 non-delivered + 7 cancelled-delivered anomalies)
    COUNT(CASE WHEN is_delivered = FALSE AND order_delivered_customer_date IS NULL THEN 1 END) AS non_delivered_missing_timestamp_orders,
    -- Timeliness breakdown
    COUNT(CASE WHEN is_eligible_for_sla AND is_late = FALSE THEN 1 END)     AS on_time_deliveries_count,
    COUNT(CASE WHEN is_eligible_for_sla AND is_late = TRUE THEN 1 END)      AS late_deliveries_count,
    -- Compliance Rates (%)
    ROUND(
        COUNT(CASE WHEN is_eligible_for_sla AND is_late = FALSE THEN 1 END)::NUMERIC
        / NULLIF(COUNT(CASE WHEN is_eligible_for_sla THEN 1 END), 0) * 100.0, 2
    )                                                                       AS on_time_delivery_rate_pct,
    ROUND(
        COUNT(CASE WHEN is_eligible_for_sla AND is_late = TRUE THEN 1 END)::NUMERIC
        / NULLIF(COUNT(CASE WHEN is_eligible_for_sla THEN 1 END), 0) * 100.0, 2
    )                                                                       AS late_delivery_rate_pct,
    -- Lead Time Milestones (Averages across eligible cohort)
    ROUND(AVG(delivery_lead_time_days), 2)                                  AS avg_total_lead_time_days,
    ROUND(AVG(seller_dispatch_days), 2)                                     AS avg_seller_dispatch_days,
    ROUND(AVG(carrier_transit_days), 2)                                     AS avg_carrier_transit_days,
    ROUND(AVG(sla_variance_days), 2)                                        AS avg_sla_buffer_days
FROM fact_orders;


-- ------------------------------------------------------------------------------
-- 2. State-to-State Logistics Corridor Performance (Inter-state vs Intra-state)
-- Business Definition:
--   - Compares delivery lead times and late delivery risk across logistics corridors.
--   - Minimum threshold of 250 orders per corridor for statistical rigor.
--   - Ranks corridors by late delivery rate using RANK().
-- ------------------------------------------------------------------------------
WITH corridor_metrics AS (
    SELECT
        ds.state                                                            AS origin_seller_state,
        dc.state                                                            AS destination_customer_state,
        CASE 
            WHEN ds.state = dc.state THEN 'Intra-State' 
            ELSE 'Inter-State' 
        END                                                                 AS corridor_type,
        COUNT(fo.order_id)                                                  AS orders_in_corridor,
        COUNT(CASE WHEN fo.is_eligible_for_sla AND fo.is_late THEN 1 END)   AS late_orders_count,
        ROUND(
            COUNT(CASE WHEN fo.is_eligible_for_sla AND fo.is_late THEN 1 END)::NUMERIC
            / NULLIF(COUNT(CASE WHEN fo.is_eligible_for_sla THEN 1 END), 0) * 100.0, 2
        )                                                                   AS corridor_late_rate_pct,
        ROUND(AVG(fo.delivery_lead_time_days), 1)                           AS avg_corridor_lead_time_days,
        ROUND(AVG(fo.carrier_transit_days), 1)                              AS avg_carrier_transit_days,
        ROUND(AVG(fo.seller_dispatch_days), 1)                             AS avg_seller_dispatch_days
    FROM fact_orders fo
    JOIN dim_customers dc ON fo.customer_key = dc.customer_key
    JOIN fact_order_items foi ON fo.order_id = foi.order_id
    JOIN dim_sellers ds ON foi.seller_key = ds.seller_key
    WHERE fo.is_eligible_for_sla = TRUE
    GROUP BY ds.state, dc.state
    HAVING COUNT(fo.order_id) >= 250
),
ranked_corridors AS (
    SELECT
        origin_seller_state,
        destination_customer_state,
        corridor_type,
        orders_in_corridor,
        late_orders_count,
        corridor_late_rate_pct,
        avg_corridor_lead_time_days,
        avg_carrier_transit_days,
        avg_seller_dispatch_days,
        RANK() OVER (ORDER BY corridor_late_rate_pct DESC)                  AS rank_highest_delay_risk,
        RANK() OVER (ORDER BY avg_corridor_lead_time_days ASC)              AS rank_fastest_lead_time
    FROM corridor_metrics
)
SELECT *
FROM ranked_corridors
ORDER BY rank_highest_delay_risk
LIMIT 20;


-- ------------------------------------------------------------------------------
-- 3. Seller Fulfillment Lead Time vs Carrier Transit Breakdown
-- Business Definition:
--   - Identifies whether delivery delays originate at seller dispatch
--     or during carrier transit (Correios logistics bottlenecks).
-- ------------------------------------------------------------------------------
SELECT
    CASE 
        WHEN seller_dispatch_days > 5.0 THEN 'Slow Seller Dispatch (>5d)'
        WHEN seller_dispatch_days BETWEEN 2.0 AND 5.0 THEN 'Normal Seller Dispatch (2-5d)'
        ELSE 'Fast Seller Dispatch (<2d)'
    END AS seller_fulfillment_speed,
    COUNT(order_id)                                                         AS order_count,
    ROUND(AVG(seller_dispatch_days), 2)                                     AS avg_seller_dispatch_days,
    ROUND(AVG(carrier_transit_days), 2)                                     AS avg_carrier_transit_days,
    ROUND(AVG(delivery_lead_time_days), 2)                                  AS avg_total_lead_time_days,
    ROUND(
        COUNT(CASE WHEN is_late THEN 1 END)::NUMERIC 
        / NULLIF(COUNT(order_id), 0) * 100.0, 2
    )                                                                       AS late_rate_pct
FROM fact_orders
WHERE is_eligible_for_sla = TRUE
  AND seller_dispatch_days IS NOT NULL
  AND carrier_transit_days IS NOT NULL
GROUP BY 
    CASE 
        WHEN seller_dispatch_days > 5.0 THEN 'Slow Seller Dispatch (>5d)'
        WHEN seller_dispatch_days BETWEEN 2.0 AND 5.0 THEN 'Normal Seller Dispatch (2-5d)'
        ELSE 'Fast Seller Dispatch (<2d)'
    END
ORDER BY avg_seller_dispatch_days DESC;
