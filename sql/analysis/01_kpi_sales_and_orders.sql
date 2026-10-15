-- ==============================================================================
-- CommerceLens AI — SQL Analytics: Sales and Order Performance
-- Script: sql/analysis/01_kpi_sales_and_orders.sql
-- Layer: Analytical Query Suite
-- Techniques: CTEs, Multi-table Joins, Window Functions (LAG, DENSE_RANK, NTILE),
--             Conditional Aggregation, Moving Averages, Cumulative Sums.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Monthly Sales Performance, MoM Growth & Moving Averages
-- Business Definition:
--   - Delivered GMV: Sum of item merchandise prices for orders successfully delivered.
--   - Delivered Orders: Count of distinct delivered orders.
--   - AOV (Average Order Value): Delivered GMV / Distinct Delivered Orders.
--   - MoM Growth %: Percentage change in Delivered GMV compared to the previous month.
--   - 3-Month Moving Average GMV: Trailing 3-month window average to smooth volatility.
-- ------------------------------------------------------------------------------
WITH monthly_metrics AS (
    SELECT
        d.year,
        d.month,
        d.month_year,
        COUNT(DISTINCT fo.order_id)                                         AS total_orders_placed,
        COUNT(DISTINCT CASE WHEN fo.is_delivered THEN fo.order_id END)      AS delivered_orders_count,
        SUM(CASE WHEN fo.is_delivered THEN fo.total_item_merchandise_value ELSE 0 END) AS delivered_gmv,
        SUM(CASE WHEN fo.is_delivered THEN fo.total_freight_value ELSE 0 END)          AS delivered_freight,
        SUM(fo.total_payment_value)                                         AS total_payments_collected,
        COUNT(DISTINCT fo.customer_key)                                     AS unique_ordering_customers
    FROM fact_orders fo
    JOIN dim_date d ON fo.purchase_date_key = d.date_key
    GROUP BY d.year, d.month, d.month_year
),
monthly_with_windows AS (
    SELECT
        year,
        month,
        month_year,
        total_orders_placed,
        delivered_orders_count,
        delivered_gmv,
        delivered_freight,
        total_payments_collected,
        unique_ordering_customers,
        -- Average Order Value (AOV)
        ROUND(
            CASE 
                WHEN delivered_orders_count > 0 
                THEN delivered_gmv / delivered_orders_count 
                ELSE 0 
            END, 2
        ) AS aov,
        -- Previous Month GMV via LAG()
        LAG(delivered_gmv, 1) OVER (ORDER BY year, month) AS prev_month_gmv,
        -- Month-over-Month GMV Growth Rate %
        ROUND(
            (delivered_gmv - LAG(delivered_gmv, 1) OVER (ORDER BY year, month))
            / NULLIF(LAG(delivered_gmv, 1) OVER (ORDER BY year, month), 0) * 100.0, 2
        ) AS mom_gmv_growth_pct,
        -- 3-Month Moving Average of GMV
        ROUND(
            AVG(delivered_gmv) OVER (
                ORDER BY year, month 
                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
            ), 2
        ) AS moving_avg_3m_gmv,
        -- Year-to-Date (YTD) Cumulative GMV
        ROUND(
            SUM(delivered_gmv) OVER (
                PARTITION BY year 
                ORDER BY month 
                ROWS UNBOUNDED PRECEDING
            ), 2
        ) AS ytd_cumulative_gmv
    FROM monthly_metrics
)
SELECT *
FROM monthly_with_windows
ORDER BY year, month;


-- ------------------------------------------------------------------------------
-- 2. Top and Bottom Product Categories by Merchandise Value (Pareto & Rankings)
-- Business Definition:
--   - Categories ranked by total delivered merchandise value (GMV).
--   - Includes minimum order volume threshold (HAVING >= 50 items) to prevent
--     small-sample outliers from skewing bottom rankings.
--   - Computes cumulative contribution percentage (Pareto 80/20 rule).
-- ------------------------------------------------------------------------------
WITH category_aggregates AS (
    SELECT
        COALESCE(dp.category_name_english, '[Uncategorized]')   AS category_name,
        COUNT(DISTINCT foi.order_id)                            AS distinct_orders_count,
        COUNT(foi.order_item_key)                               AS total_units_sold,
        SUM(foi.price)                                          AS total_item_merchandise_value,
        SUM(foi.freight_value)                                  AS total_freight_value,
        ROUND(AVG(foi.price), 2)                                AS avg_item_price,
        ROUND(
            SUM(foi.freight_value) / NULLIF(SUM(foi.price), 0) * 100.0, 2
        )                                                       AS freight_to_price_ratio_pct
    FROM fact_order_items foi
    JOIN fact_orders fo ON foi.order_id = fo.order_id
    JOIN dim_products dp ON foi.product_key = dp.product_key
    WHERE fo.is_delivered = TRUE
    GROUP BY COALESCE(dp.category_name_english, '[Uncategorized]')
    HAVING COUNT(foi.order_item_key) >= 50
),
ranked_categories AS (
    SELECT
        category_name,
        distinct_orders_count,
        total_units_sold,
        total_item_merchandise_value,
        total_freight_value,
        avg_item_price,
        freight_to_price_ratio_pct,
        DENSE_RANK() OVER (ORDER BY total_item_merchandise_value DESC) AS rank_highest_gmv,
        DENSE_RANK() OVER (ORDER BY total_item_merchandise_value ASC)  AS rank_lowest_gmv,
        SUM(total_item_merchandise_value) OVER ()                      AS total_eligible_gmv,
        SUM(total_item_merchandise_value) OVER (
            ORDER BY total_item_merchandise_value DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_gmv
    FROM category_aggregates
)
SELECT
    rank_highest_gmv,
    category_name,
    distinct_orders_count,
    total_units_sold,
    total_item_merchandise_value,
    total_freight_value,
    avg_item_price,
    freight_to_price_ratio_pct,
    ROUND((cumulative_gmv / total_eligible_gmv) * 100.0, 2) AS cumulative_gmv_pct
FROM ranked_categories
ORDER BY rank_highest_gmv
LIMIT 20;


-- ------------------------------------------------------------------------------
-- 3. Seller Concentration and Performance Quartiles
-- Business Definition:
--   - Assesses marketplace seller concentration (Gini/Pareto dynamics).
--   - Classifies sellers into performance quartiles using NTILE(4).
-- ------------------------------------------------------------------------------
WITH seller_metrics AS (
    SELECT
        ds.seller_id,
        ds.state                                                    AS seller_state,
        COUNT(DISTINCT foi.order_id)                                AS total_orders_fulfilled,
        COUNT(foi.order_item_key)                                   AS total_items_sold,
        SUM(foi.price)                                              AS total_seller_gmv,
        ROUND(AVG(foi.price), 2)                                    AS avg_item_price,
        ROUND(AVG(fo.delivery_lead_time_days), 1)                   AS avg_delivery_days
    FROM fact_order_items foi
    JOIN fact_orders fo ON foi.order_id = fo.order_id
    JOIN dim_sellers ds ON foi.seller_key = ds.seller_key
    WHERE fo.is_delivered = TRUE
    GROUP BY ds.seller_id, ds.state
),
seller_quartiles AS (
    SELECT
        seller_id,
        seller_state,
        total_orders_fulfilled,
        total_items_sold,
        total_seller_gmv,
        avg_item_price,
        avg_delivery_days,
        NTILE(4) OVER (ORDER BY total_seller_gmv DESC)              AS gmv_quartile,
        DENSE_RANK() OVER (ORDER BY total_seller_gmv DESC)          AS seller_rank
    FROM seller_metrics
)
SELECT
    gmv_quartile,
    COUNT(seller_id)                                                AS seller_count,
    ROUND(SUM(total_seller_gmv), 2)                                 AS quartile_total_gmv,
    ROUND(AVG(total_seller_gmv), 2)                                 AS quartile_avg_gmv_per_seller,
    ROUND(AVG(total_orders_fulfilled), 1)                           AS quartile_avg_orders,
    ROUND(
        SUM(total_seller_gmv) / (SELECT SUM(total_seller_gmv) FROM seller_metrics) * 100.0, 2
    )                                                               AS pct_of_marketplace_gmv
FROM seller_quartiles
GROUP BY gmv_quartile
ORDER BY gmv_quartile;
