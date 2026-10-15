"""
KPI Calculation and Reconciliation Logic for CommerceLens AI.

Executes validated business KPI queries against the dimensional model,
enforces anti-fan-out grain control, and verifies data integrity.
"""

from typing import Any, Dict
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def calculate_reconciliation_audit(engine: Engine) -> pd.DataFrame:
    """
    Run the anti-fan-out financial reconciliation audit.
    Proves that pre-aggregated fact_orders totals exactly equal
    line-item and line-payment totals with zero variance.
    """
    query = """
    SELECT
        'Item Merchandise Value (GMV)' AS metric_name,
        ROUND(SUM(fo.total_item_merchandise_value), 2) AS fact_orders_total,
        ROUND((SELECT SUM(price) FROM fact_order_items), 2) AS line_fact_total,
        ROUND(SUM(fo.total_item_merchandise_value) - (SELECT SUM(price) FROM fact_order_items), 2) AS variance
    FROM fact_orders fo

    UNION ALL

    SELECT
        'Freight Value',
        ROUND(SUM(fo.total_freight_value), 2),
        ROUND((SELECT SUM(freight_value) FROM fact_order_items), 2),
        ROUND(SUM(fo.total_freight_value) - (SELECT SUM(freight_value) FROM fact_order_items), 2)
    FROM fact_orders fo

    UNION ALL

    SELECT
        'Payment Value',
        ROUND(SUM(fo.total_payment_value), 2),
        ROUND((SELECT SUM(payment_value) FROM fact_payments), 2),
        ROUND(SUM(fo.total_payment_value) - (SELECT SUM(payment_value) FROM fact_payments), 2)
    FROM fact_orders fo;
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


def calculate_delivery_sla_summary(engine: Engine) -> Dict[str, Any]:
    """
    Calculate delivery operations KPIs with strict denominator isolation.
    - Excludes the 8 delivered orders with missing customer delivery date from SLA compliance.
    """
    query = """
    SELECT
        COUNT(order_id) AS total_orders,
        COUNT(CASE WHEN is_delivered THEN 1 END) AS total_delivered_orders,
        COUNT(CASE WHEN is_eligible_for_sla THEN 1 END) AS sla_eligible_delivered_orders,
        COUNT(CASE WHEN is_delivered AND order_delivered_customer_date IS NULL THEN 1 END) AS delivered_missing_timestamp_orders,
        COUNT(CASE WHEN is_eligible_for_sla AND is_late = FALSE THEN 1 END) AS on_time_orders_count,
        COUNT(CASE WHEN is_eligible_for_sla AND is_late = TRUE THEN 1 END) AS late_orders_count,
        ROUND(
            (COUNT(CASE WHEN is_eligible_for_sla AND is_late = FALSE THEN 1 END) * 100.0)
            / NULLIF(COUNT(CASE WHEN is_eligible_for_sla THEN 1 END), 0), 2
        ) AS on_time_delivery_rate_pct,
        ROUND(
            (COUNT(CASE WHEN is_eligible_for_sla AND is_late = TRUE THEN 1 END) * 100.0)
            / NULLIF(COUNT(CASE WHEN is_eligible_for_sla THEN 1 END), 0), 2
        ) AS late_delivery_rate_pct,
        ROUND(AVG(delivery_lead_time_days), 2) AS avg_delivery_lead_time_days,
        ROUND(AVG(carrier_transit_days), 2) AS avg_carrier_transit_days,
        ROUND(AVG(seller_dispatch_days), 2) AS avg_seller_dispatch_days,
        ROUND(AVG(sla_variance_days), 2) AS avg_sla_variance_buffer_days
    FROM fact_orders;
    """
    with engine.connect() as conn:
        result = conn.execute(text(query)).mappings().first()
        return dict(result) if result else {}


def calculate_sales_kpis(engine: Engine) -> Dict[str, Any]:
    """
    Calculate top-level commercial sales metrics at marketplace grain.
    """
    query = """
    SELECT
        COUNT(DISTINCT order_id) AS total_orders_placed,
        COUNT(DISTINCT CASE WHEN is_delivered THEN order_id END) AS delivered_orders_count,
        ROUND(SUM(CASE WHEN is_delivered THEN total_item_merchandise_value ELSE 0 END), 2) AS delivered_item_merchandise_value,
        ROUND(SUM(CASE WHEN is_delivered THEN total_freight_value ELSE 0 END), 2) AS delivered_freight_value,
        ROUND(SUM(total_payment_value), 2) AS total_payments_collected,
        ROUND(
            SUM(CASE WHEN is_delivered THEN total_item_merchandise_value ELSE 0 END)
            / NULLIF(COUNT(DISTINCT CASE WHEN is_delivered THEN order_id END), 0), 2
        ) AS aov_delivered
    FROM fact_orders;
    """
    with engine.connect() as conn:
        result = conn.execute(text(query)).mappings().first()
        return dict(result) if result else {}


def demonstrate_anti_fanout_impact(engine: Engine, sample_order_id: str) -> Dict[str, Any]:
    """
    Compare naive unaggregated join vs CTE pre-aggregation for a given multi-item / multi-payment order.
    Demonstrates the exact mathematical inflation error caused by Cartesian explosion.
    """
    naive_query = text("""
        SELECT
            COUNT(*) AS cartesian_rows,
            SUM(foi.price) AS naive_merchandise_value,
            SUM(fp.payment_value) AS naive_payment_value
        FROM fact_order_items foi
        JOIN fact_payments fp ON foi.order_id = fp.order_id
        WHERE foi.order_id = :order_id
    """)

    correct_query = text("""
        SELECT
            fo.total_items_count,
            fo.payment_slices_count,
            fo.total_item_merchandise_value AS correct_merchandise_value,
            fo.total_payment_value AS correct_payment_value
        FROM fact_orders fo
        WHERE fo.order_id = :order_id
    """)

    with engine.connect() as conn:
        naive_res = conn.execute(naive_query, {"order_id": sample_order_id}).mappings().first()
        correct_res = conn.execute(correct_query, {"order_id": sample_order_id}).mappings().first()

    return {
        "order_id": sample_order_id,
        "items_count": correct_res["total_items_count"] if correct_res else 0,
        "payments_count": correct_res["payment_slices_count"] if correct_res else 0,
        "cartesian_rows": naive_res["cartesian_rows"] if naive_res else 0,
        "correct_merchandise_value": float(correct_res["correct_merchandise_value"]) if correct_res else 0.0,
        "naive_merchandise_value": float(naive_res["naive_merchandise_value"]) if naive_res else 0.0,
        "correct_payment_value": float(correct_res["correct_payment_value"]) if correct_res else 0.0,
        "naive_payment_value": float(naive_res["naive_payment_value"]) if naive_res else 0.0,
    }
