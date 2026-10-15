-- ==============================================================================
-- CommerceLens AI — SQL Analytics: Operational Quality & Reconciliation Audit
-- Script: sql/analysis/04_operational_quality_and_reconciliation.sql
-- Layer: Analytical & Audit Suite
-- Techniques: Fan-out Proof Query, Mathematical Reconciliation, Grain Verification,
--             Zero-Value Retention Audit, Referential Integrity Verification.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Order Status Distribution & Exception Rates
-- Business Definition:
--   - Tracks order lifecycle status breakdown across the entire 99,441 orders.
--   - Strictly reports Cancellation Rate and Unavailable Rate separately.
-- ------------------------------------------------------------------------------
SELECT
    order_status,
    COUNT(order_id)                                                         AS order_count,
    ROUND(
        COUNT(order_id)::NUMERIC 
        / (SELECT COUNT(*) FROM fact_orders) * 100.0, 3
    )                                                                       AS pct_of_total_orders
FROM fact_orders
GROUP BY order_status
ORDER BY order_count DESC;


-- ------------------------------------------------------------------------------
-- 2. Anti-Fan-Out Demonstration: The Danger of Joining Multi-Item & Multi-Payment
-- Interview / Architecture Proof:
--   - Orders with both multiple items (N > 1) and multiple payments (M > 1) create
--     a Cartesian product of (N x M) rows if joined naively before aggregation!
--   - This query demonstrates the exact dollar error introduced by a naive join
--     versus the mathematically correct CTE pre-aggregation.
-- ------------------------------------------------------------------------------
WITH problematic_orders AS (
    -- Identify orders that have BOTH multiple items and multiple payments
    SELECT
        foi.order_id
    FROM fact_order_items foi
    GROUP BY foi.order_id
    HAVING COUNT(foi.order_item_id) > 1
    INTERSECT
    SELECT
        fp.order_id
    FROM fact_payments fp
    GROUP BY fp.order_id
    HAVING COUNT(fp.payment_sequential) > 1
),
sample_problem_order AS (
    SELECT order_id FROM problematic_orders LIMIT 1
),
naive_fanout_join AS (
    -- NAIVE / BROKEN APPROACH: Joining unaggregated items and payments
    SELECT
        foi.order_id,
        COUNT(*)                            AS cartesian_row_count,
        SUM(foi.price)                      AS naive_sum_merchandise_price,
        SUM(fp.payment_value)               AS naive_sum_payment_value
    FROM fact_order_items foi
    JOIN fact_payments fp ON foi.order_id = fp.order_id
    WHERE foi.order_id IN (SELECT order_id FROM sample_problem_order)
    GROUP BY foi.order_id
),
controlled_grain_aggregation AS (
    -- CORRECT / ARCHITECTED APPROACH: fact_orders pre-aggregated grain
    SELECT
        fo.order_id,
        fo.total_items_count,
        fo.payment_slices_count,
        fo.total_item_merchandise_value     AS correct_item_merchandise_value,
        fo.total_payment_value              AS correct_payment_value
    FROM fact_orders fo
    WHERE fo.order_id IN (SELECT order_id FROM sample_problem_order)
)
SELECT
    c.order_id,
    c.total_items_count,
    c.payment_slices_count,
    n.cartesian_row_count                   AS naive_join_row_count,
    c.correct_item_merchandise_value,
    n.naive_sum_merchandise_price,
    ROUND(n.naive_sum_merchandise_price - c.correct_item_merchandise_value, 2) AS merchandise_inflation_error,
    c.correct_payment_value,
    n.naive_sum_payment_value,
    ROUND(n.naive_sum_payment_value - c.correct_payment_value, 2)              AS payment_inflation_error
FROM controlled_grain_aggregation c
JOIN naive_fanout_join n ON c.order_id = n.order_id;


-- ------------------------------------------------------------------------------
-- 3. Complete Financial Reconciliation Audit
-- Verifies that fact_orders measures perfectly match item and payment line facts.
-- Discrepancy must equal EXACTLY 0.00 across the entire dataset!
-- ------------------------------------------------------------------------------
SELECT
    'Item Merchandise Value (GMV)'                                  AS financial_metric,
    ROUND(SUM(fo.total_item_merchandise_value), 2)                  AS fact_orders_sum,
    ROUND(SUM(foi.price), 2)                                        AS underlying_line_fact_sum,
    ROUND(SUM(fo.total_item_merchandise_value) - SUM(foi.price), 2) AS variance
FROM fact_orders fo
FULL OUTER JOIN (
    SELECT SUM(price) AS price FROM fact_order_items
) foi ON 1=1
GROUP BY foi.price

UNION ALL

SELECT
    'Freight Value',
    ROUND(SUM(fo.total_freight_value), 2),
    ROUND(SUM(foi.freight_value), 2),
    ROUND(SUM(fo.total_freight_value) - SUM(foi.freight_value), 2)
FROM fact_orders fo
FULL OUTER JOIN (
    SELECT SUM(freight_value) AS freight_value FROM fact_order_items
) foi ON 1=1
GROUP BY foi.freight_value

UNION ALL

SELECT
    'Payment Value',
    ROUND(SUM(fo.total_payment_value), 2),
    ROUND(SUM(fp.payment_value), 2),
    ROUND(SUM(fo.total_payment_value) - SUM(fp.payment_value), 2)
FROM fact_orders fo
FULL OUTER JOIN (
    SELECT SUM(payment_value) AS payment_value FROM fact_payments
) fp ON 1=1
GROUP BY fp.payment_value;


-- ------------------------------------------------------------------------------
-- 4. Zero-Value Voucher Payment Retention Audit
-- Verifies that the 9 legitimate voucher transactions with payment_value = 0.00
-- were strictly retained and not filtered out.
-- ------------------------------------------------------------------------------
SELECT
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value
FROM fact_payments
WHERE payment_value = 0.00;


-- ------------------------------------------------------------------------------
-- 5. Foreign Key Integrity & Orphaned Record Check
-- Asserts 100% referential integrity across dimensional and fact relationships.
-- Every check should return 0 orphaned records.
-- ------------------------------------------------------------------------------
SELECT 'Orders with missing customer' AS check_name, COUNT(*) AS orphan_count
FROM fact_orders fo
LEFT JOIN dim_customers dc ON fo.customer_key = dc.customer_key
WHERE dc.customer_key IS NULL

UNION ALL

SELECT 'Order items with missing order', COUNT(*)
FROM fact_order_items foi
LEFT JOIN fact_orders fo ON foi.order_id = fo.order_id
WHERE fo.order_id IS NULL

UNION ALL

SELECT 'Order items with missing product', COUNT(*)
FROM fact_order_items foi
LEFT JOIN dim_products dp ON foi.product_key = dp.product_key
WHERE dp.product_key IS NULL

UNION ALL

SELECT 'Order items with missing seller', COUNT(*)
FROM fact_order_items foi
LEFT JOIN dim_sellers ds ON foi.seller_key = ds.seller_key
WHERE ds.seller_key IS NULL

UNION ALL

SELECT 'Payments with missing order', COUNT(*)
FROM fact_payments fp
LEFT JOIN fact_orders fo ON fp.order_id = fo.order_id
WHERE fo.order_id IS NULL

UNION ALL

SELECT 'Reviews with missing order', COUNT(*)
FROM fact_reviews fr
LEFT JOIN fact_orders fo ON fr.order_id = fo.order_id
WHERE fo.order_id IS NULL;
