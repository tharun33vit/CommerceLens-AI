"""
Comprehensive Live PostgreSQL Validation & Reconciliation Script for CommerceLens AI.

Executes live database queries to:
1. Validate views and query outputs.
2. Check aggregate and per-order financial reconciliations.
3. Validate foreign-key referential integrity (orphan records).
4. Demonstrate anti-fan-out error metrics.
5. Verify zero-value payments and SLA compliance denominators.
"""

import sys
sys.path.insert(0, "src")

import pandas as pd
from sqlalchemy import text
from commercelens.analytics.db import create_db_engine, mask_connection_url
from commercelens.analytics.kpis import (
    calculate_delivery_sla_summary,
    calculate_reconciliation_audit,
    calculate_sales_kpis,
)

def main():
    engine = create_db_engine()
    print(f"Connected to live PostgreSQL: {mask_connection_url(str(engine.url))}\n")

    # 1. Views Verification
    print("=== 1. ANALYTICAL VIEWS VERIFICATION ===")
    views = [
        "v_monthly_sales_performance",
        "v_category_merchandise_performance",
        "v_delivery_sla_operations",
        "v_customer_repurchase_rfm",
        "v_csat_and_delivery_correlation",
        "v_reconciliation_audit",
    ]
    with engine.connect() as conn:
        for v in views:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {v}")).scalar()
            print(f"View {v:36}: {count:>6} rows")

    # 2. Financial Aggregate Reconciliation
    print("\n=== 2. FINANCIAL AGGREGATE RECONCILIATION ===")
    reconciliation_df = calculate_reconciliation_audit(engine)
    print(reconciliation_df.to_string(index=False))

    # 3. Individual Order-Level Reconciliation
    print("\n=== 3. INDIVIDUAL ORDER-LEVEL RECONCILIATION ===")
    order_recon_query = """
    WITH item_check AS (
        SELECT 
            order_id,
            ROUND(SUM(price), 2) AS item_sum,
            ROUND(SUM(freight_value), 2) AS freight_sum
        FROM fact_order_items
        GROUP BY order_id
    ),
    payment_check AS (
        SELECT 
            order_id,
            ROUND(SUM(payment_value), 2) AS payment_sum
        FROM fact_payments
        GROUP BY order_id
    )
    SELECT
        COUNT(*) AS total_orders_checked,
        COUNT(CASE WHEN ROUND(fo.total_item_merchandise_value, 2) = COALESCE(ic.item_sum, 0.0) THEN 1 END) AS matching_item_orders,
        COUNT(CASE WHEN ROUND(fo.total_item_merchandise_value, 2) != COALESCE(ic.item_sum, 0.0) THEN 1 END) AS mismatch_item_orders,
        COUNT(CASE WHEN ROUND(fo.total_freight_value, 2) = COALESCE(ic.freight_sum, 0.0) THEN 1 END) AS matching_freight_orders,
        COUNT(CASE WHEN ROUND(fo.total_freight_value, 2) != COALESCE(ic.freight_sum, 0.0) THEN 1 END) AS mismatch_freight_orders,
        COUNT(CASE WHEN ROUND(fo.total_payment_value, 2) = COALESCE(pc.payment_sum, 0.0) THEN 1 END) AS matching_payment_orders,
        COUNT(CASE WHEN ROUND(fo.total_payment_value, 2) != COALESCE(pc.payment_sum, 0.0) THEN 1 END) AS mismatch_payment_orders
    FROM fact_orders fo
    LEFT JOIN item_check ic ON fo.order_id = ic.order_id
    LEFT JOIN payment_check pc ON fo.order_id = pc.order_id;
    """
    with engine.connect() as conn:
        res = conn.execute(text(order_recon_query)).mappings().first()
        for k, v in res.items():
            print(f"  {k:30}: {v}")

    # Check order items vs payments relationship (Order GMV vs Payment Total at Order Level)
    gross_vs_payment_query = """
    SELECT
        COUNT(*) AS total_orders,
        COUNT(CASE WHEN total_order_gross_value = total_payment_value THEN 1 END) AS exact_payment_match_orders,
        COUNT(CASE WHEN total_order_gross_value != total_payment_value THEN 1 END) AS payment_variance_orders,
        ROUND(SUM(total_order_gross_value), 2) AS total_gross_value_sum,
        ROUND(SUM(total_payment_value), 2) AS total_payment_value_sum,
        ROUND(SUM(total_payment_value) - SUM(total_order_gross_value), 2) AS overall_payment_to_gross_difference
    FROM fact_orders;
    """
    with engine.connect() as conn:
        gross_res = conn.execute(text(gross_vs_payment_query)).mappings().first()
        print("\n  Order Gross Value (Merchandise + Freight) vs Payments:")
        for k, v in gross_res.items():
            print(f"    {k:35}: {v}")

    # 4. Anti-Fan-Out Demonstration
    print("\n=== 4. LIVE ANTI-FAN-OUT PROOF QUERY ===")
    fanout_query = """
    WITH problematic_orders AS (
        SELECT foi.order_id
        FROM fact_order_items foi
        GROUP BY foi.order_id
        HAVING COUNT(foi.order_item_id) > 1
        INTERSECT
        SELECT fp.order_id
        FROM fact_payments fp
        GROUP BY fp.order_id
        HAVING COUNT(fp.payment_sequential) > 1
    ),
    sample_problem_order AS (
        SELECT order_id FROM problematic_orders ORDER BY order_id LIMIT 1
    ),
    naive_fanout_join AS (
        SELECT
            foi.order_id,
            COUNT(*) AS cartesian_row_count,
            SUM(foi.price) AS naive_sum_merchandise_price,
            SUM(fp.payment_value) AS naive_sum_payment_value
        FROM fact_order_items foi
        JOIN fact_payments fp ON foi.order_id = fp.order_id
        WHERE foi.order_id IN (SELECT order_id FROM sample_problem_order)
        GROUP BY foi.order_id
    ),
    controlled_grain_aggregation AS (
        SELECT
            fo.order_id,
            fo.total_items_count,
            fo.payment_slices_count,
            fo.total_item_merchandise_value AS correct_item_merchandise_value,
            fo.total_payment_value AS correct_payment_value
        FROM fact_orders fo
        WHERE fo.order_id IN (SELECT order_id FROM sample_problem_order)
    )
    SELECT
        c.order_id,
        c.total_items_count,
        c.payment_slices_count,
        n.cartesian_row_count,
        c.correct_item_merchandise_value,
        n.naive_sum_merchandise_price,
        ROUND(n.naive_sum_merchandise_price - c.correct_item_merchandise_value, 2) AS merchandise_inflation_error,
        c.correct_payment_value,
        n.naive_sum_payment_value,
        ROUND(n.naive_sum_payment_value - c.correct_payment_value, 2) AS payment_inflation_error
    FROM controlled_grain_aggregation c
    JOIN naive_fanout_join n ON c.order_id = n.order_id;
    """
    with engine.connect() as conn:
        fo_row = conn.execute(text(fanout_query)).mappings().first()
        for k, v in fo_row.items():
            print(f"  {k:30}: {v}")

    # 5. Delivery SLA Summary (Strict Denominator)
    print("\n=== 5. DELIVERY SLA METRICS (STRICT DENOMINATOR) ===")
    sla_res = calculate_delivery_sla_summary(engine)
    for k, v in sla_res.items():
        print(f"  {k:35}: {v}")

    # 6. Foreign-Key Referential Integrity (Orphans Check)
    print("\n=== 6. FOREIGN-KEY REFERENTIAL INTEGRITY (ORPHANS CHECK) ===")
    orphan_query = """
    SELECT 'Orders missing dim_customers' AS check_name, COUNT(*) AS orphan_count
    FROM fact_orders fo LEFT JOIN dim_customers dc ON fo.customer_key = dc.customer_key
    WHERE dc.customer_key IS NULL
    UNION ALL
    SELECT 'Orders missing dim_date', COUNT(*)
    FROM fact_orders fo LEFT JOIN dim_date dd ON fo.purchase_date_key = dd.date_key
    WHERE dd.date_key IS NULL
    UNION ALL
    SELECT 'Items missing fact_orders', COUNT(*)
    FROM fact_order_items foi LEFT JOIN fact_orders fo ON foi.order_id = fo.order_id
    WHERE fo.order_id IS NULL
    UNION ALL
    SELECT 'Items missing dim_products', COUNT(*)
    FROM fact_order_items foi LEFT JOIN dim_products dp ON foi.product_key = dp.product_key
    WHERE dp.product_key IS NULL
    UNION ALL
    SELECT 'Items missing dim_sellers', COUNT(*)
    FROM fact_order_items foi LEFT JOIN dim_sellers ds ON foi.seller_key = ds.seller_key
    WHERE ds.seller_key IS NULL
    UNION ALL
    SELECT 'Payments missing fact_orders', COUNT(*)
    FROM fact_payments fp LEFT JOIN fact_orders fo ON fp.order_id = fo.order_id
    WHERE fo.order_id IS NULL
    UNION ALL
    SELECT 'Reviews missing fact_orders', COUNT(*)
    FROM fact_reviews fr LEFT JOIN fact_orders fo ON fr.order_id = fo.order_id
    WHERE fo.order_id IS NULL;
    """
    with engine.connect() as conn:
        orphans = conn.execute(text(orphan_query)).fetchall()
        for check_name, orphan_count in orphans:
            print(f"  {check_name:35}: {orphan_count} orphans")

    # 7. Zero-Value Payment Audit
    print("\n=== 7. ZERO-VALUE PAYMENT AUDIT ===")
    zero_query = """
    SELECT payment_type, COUNT(*) AS count, SUM(payment_value) AS sum_val
    FROM fact_payments
    WHERE payment_value = 0.00
    GROUP BY payment_type;
    """
    with engine.connect() as conn:
        zero_rows = conn.execute(text(zero_query)).fetchall()
        for r in zero_rows:
            print(f"  Type: {r[0]:15} Count: {r[1]} Sum: {r[2]}")

if __name__ == "__main__":
    main()
