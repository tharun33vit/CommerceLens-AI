"""
Live PostgreSQL Integration Test Suite for CommerceLens AI.

Executes real database queries against the local PostgreSQL server (localhost:5432)
to validate:
1. Live database connectivity and dialect verification.
2. Verified table row counts for all staging, dimension, and fact tables.
3. Foreign-key referential integrity (zero orphaned records).
4. Aggregate financial reconciliation (0.00 variance between facts and line items).
5. Exact order-level reconciliation across all 99,441 orders.
6. Strict Delivery SLA compliance calculation (96,470 eligible orders; 8 excluded).
7. Zero-value payment distribution (6 vouchers, 3 not_defined).
8. Live analytical views querying and row validation.
"""

from pathlib import Path
import pytest
from sqlalchemy import text
from commercelens.analytics.db import (
    check_connection,
    create_db_engine,
    get_database_url,
    mask_connection_url,
)
from commercelens.analytics.kpis import (
    calculate_delivery_sla_summary,
    calculate_reconciliation_audit,
    calculate_sales_kpis,
    demonstrate_anti_fanout_impact,
)
from commercelens.analytics.loader import EXPECTED_STAGING_ROW_COUNTS

EXPECTED_DIMENSIONAL_COUNTS = {
    "dim_customers": 99441,
    "dim_sellers": 3095,
    "dim_products": 32951,
    "dim_geography": 19010,
    "dim_date": 1096,
    "fact_orders": 99441,
    "fact_order_items": 112650,
    "fact_payments": 103886,
    "fact_reviews": 99224,
}


@pytest.fixture(scope="module")
def postgres_engine():
    """Returns SQLAlchemy engine connected to live PostgreSQL commercelens_db."""
    url = get_database_url()
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL connection not configured in environment.")

    engine = create_db_engine()
    is_connected, msg = check_connection(engine)
    if not is_connected:
        pytest.skip(f"Live PostgreSQL server is unreachable: {msg}")

    return engine


def test_live_postgres_connection(postgres_engine):
    """Verify live connection to PostgreSQL 18 on localhost."""
    with postgres_engine.connect() as conn:
        version = conn.execute(text("SELECT version();")).scalar()
        assert "PostgreSQL" in version
        assert "18" in version or "PostgreSQL 1" in version


@pytest.mark.parametrize("table_name, expected_count", EXPECTED_STAGING_ROW_COUNTS.items())
def test_live_staging_row_counts(postgres_engine, table_name, expected_count):
    """Verify exact row counts in all staging tables on live PostgreSQL."""
    with postgres_engine.connect() as conn:
        actual_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name};")).scalar()
        assert actual_count == expected_count, (
            f"Staging table {table_name} count mismatch: expected {expected_count}, got {actual_count}"
        )


@pytest.mark.parametrize("table_name, expected_count", EXPECTED_DIMENSIONAL_COUNTS.items())
def test_live_dimensional_row_counts(postgres_engine, table_name, expected_count):
    """Verify exact row counts in all dimension and fact tables on live PostgreSQL."""
    with postgres_engine.connect() as conn:
        actual_count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name};")).scalar()
        assert actual_count == expected_count, (
            f"Dimensional table {table_name} count mismatch: expected {expected_count}, got {actual_count}"
        )


def test_live_financial_aggregate_reconciliation(postgres_engine):
    """Verify live financial reconciliation yields exactly 0.00 variance across the marketplace."""
    reconciliation_df = calculate_reconciliation_audit(postgres_engine)
    assert len(reconciliation_df) == 3

    for _, row in reconciliation_df.iterrows():
        assert row["variance"] == 0.0, (
            f"Live variance detected in {row['metric_name']}: {row['variance']}"
        )

    # Verify exact GMV and Payment values
    gmv_row = reconciliation_df[reconciliation_df["metric_name"].str.contains("GMV")].iloc[0]
    assert gmv_row["fact_orders_total"] == 13591643.70
    assert gmv_row["line_fact_total"] == 13591643.70


def test_live_order_level_reconciliation(postgres_engine):
    """Verify that every single order matches item and payment line facts at order grain."""
    query = text("""
        WITH item_check AS (
            SELECT order_id, ROUND(SUM(price), 2) AS item_sum, ROUND(SUM(freight_value), 2) AS freight_sum
            FROM fact_order_items GROUP BY order_id
        ),
        payment_check AS (
            SELECT order_id, ROUND(SUM(payment_value), 2) AS payment_sum
            FROM fact_payments GROUP BY order_id
        )
        SELECT
            COUNT(*) AS total_orders,
            COUNT(CASE WHEN ROUND(fo.total_item_merchandise_value, 2) = COALESCE(ic.item_sum, 0.0) THEN 1 END) AS match_items,
            COUNT(CASE WHEN ROUND(fo.total_freight_value, 2) = COALESCE(ic.freight_sum, 0.0) THEN 1 END) AS match_freight,
            COUNT(CASE WHEN ROUND(fo.total_payment_value, 2) = COALESCE(pc.payment_sum, 0.0) THEN 1 END) AS match_payments
        FROM fact_orders fo
        LEFT JOIN item_check ic ON fo.order_id = ic.order_id
        LEFT JOIN payment_check pc ON fo.order_id = pc.order_id;
    """)
    with postgres_engine.connect() as conn:
        res = conn.execute(query).mappings().first()
        assert res["total_orders"] == 99441
        assert res["match_items"] == 99441
        assert res["match_freight"] == 99441
        assert res["match_payments"] == 99441


def test_live_delivery_sla_metrics_and_denominator(postgres_engine):
    """
    Verify live Delivery SLA metrics on PostgreSQL:
    - Exactly 96,470 orders in SLA-eligible denominator (96,478 delivered - 8 missing timestamps).
    - 88,644 on-time (91.89%) and 7,826 late (8.11%).
    """
    sla = calculate_delivery_sla_summary(postgres_engine)
    assert sla["total_orders"] == 99441
    assert sla["total_delivered_orders"] == 96478
    assert sla["sla_eligible_delivered_orders"] == 96470
    assert sla["delivered_missing_timestamp_orders"] == 8
    assert sla["on_time_orders_count"] == 88644
    assert sla["late_orders_count"] == 7826
    assert float(sla["on_time_delivery_rate_pct"]) == 91.89
    assert float(sla["late_delivery_rate_pct"]) == 8.11


def test_live_zero_value_payments_breakdown(postgres_engine):
    """
    Verify exact distribution of the 9 zero-value payments:
    - 6 vouchers
    - 3 not_defined
    """
    query = text("""
        SELECT payment_type, COUNT(*) AS count
        FROM fact_payments
        WHERE payment_value = 0.00
        GROUP BY payment_type
        ORDER BY payment_type;
    """)
    with postgres_engine.connect() as conn:
        rows = dict(conn.execute(query).fetchall())
        assert rows == {"not_defined": 3, "voucher": 6}


def test_live_referential_integrity_zero_orphans(postgres_engine):
    """Verify 100% foreign key integrity (zero orphaned records) across live database."""
    orphan_query = text("""
        SELECT 'Orders missing customer' AS check_name, COUNT(*) AS cnt
        FROM fact_orders fo LEFT JOIN dim_customers dc ON fo.customer_key = dc.customer_key WHERE dc.customer_key IS NULL
        UNION ALL
        SELECT 'Orders missing date', COUNT(*)
        FROM fact_orders fo LEFT JOIN dim_date dd ON fo.purchase_date_key = dd.date_key WHERE dd.date_key IS NULL
        UNION ALL
        SELECT 'Items missing order', COUNT(*)
        FROM fact_order_items foi LEFT JOIN fact_orders fo ON foi.order_id = fo.order_id WHERE fo.order_id IS NULL
        UNION ALL
        SELECT 'Items missing product', COUNT(*)
        FROM fact_order_items foi LEFT JOIN dim_products dp ON foi.product_key = dp.product_key WHERE dp.product_key IS NULL
        UNION ALL
        SELECT 'Items missing seller', COUNT(*)
        FROM fact_order_items foi LEFT JOIN dim_sellers ds ON foi.seller_key = ds.seller_key WHERE ds.seller_key IS NULL
        UNION ALL
        SELECT 'Payments missing order', COUNT(*)
        FROM fact_payments fp LEFT JOIN fact_orders fo ON fp.order_id = fo.order_id WHERE fo.order_id IS NULL
        UNION ALL
        SELECT 'Reviews missing order', COUNT(*)
        FROM fact_reviews fr LEFT JOIN fact_orders fo ON fr.order_id = fo.order_id WHERE fo.order_id IS NULL;
    """)
    with postgres_engine.connect() as conn:
        results = conn.execute(orphan_query).fetchall()
        for name, cnt in results:
            assert cnt == 0, f"Referential integrity failure for {name}: {cnt} orphaned records"


def test_live_analytical_views_execution(postgres_engine):
    """Verify all 6 analytical views execute and return expected row counts on PostgreSQL."""
    view_expectations = {
        "v_monthly_sales_performance": 25,
        "v_category_merchandise_performance": 74,
        "v_delivery_sla_operations": 1,
        "v_customer_repurchase_rfm": 96096,
        "v_csat_and_delivery_correlation": 4,
        "v_reconciliation_audit": 6,
    }
    with postgres_engine.connect() as conn:
        for view_name, expected_rows in view_expectations.items():
            count = conn.execute(text(f"SELECT COUNT(*) FROM {view_name};")).scalar()
            assert count == expected_rows, (
                f"View {view_name} expected {expected_rows} rows, got {count}"
            )
