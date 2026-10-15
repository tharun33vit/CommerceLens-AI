"""
Automated Test Suite for Phase 2: PostgreSQL Relational Modeling & SQL Analytics.

Tests:
1. SQL script discovery, completeness, and syntax structure.
2. Connection management, URL password masking, and safe operational error handling.
3. Cleaned dataset presence, schemas, and exact row counts.
4. Primary and candidate key uniqueness (including the compound review key).
5. Strict retention of the 9 zero-value voucher payments.
6. Exclusion of the 8 delivered orders missing timestamps from SLA denominators.
7. Anti-fan-out mathematical reconciliation (CTE pre-aggregation vs naive Cartesian join).
8. KPI calculation accuracy on controlled relational fixtures.
9. Category translation provenance and null preservation.
"""

from pathlib import Path
import sqlite3
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from commercelens.analytics.db import (
    check_connection,
    create_db_engine,
    get_database_url,
    mask_connection_url,
)
from commercelens.analytics.kpis import (
    calculate_delivery_sla_summary,
    calculate_reconciliation_audit,
    demonstrate_anti_fanout_impact,
)
from commercelens.analytics.loader import (
    EXPECTED_STAGING_ROW_COUNTS,
    load_processed_dataframe,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"


# ------------------------------------------------------------------------------
# 1. SQL Scripts Verification
# ------------------------------------------------------------------------------
def test_sql_schema_and_view_files_exist():
    """Verify all required DDL, view, and analysis SQL files exist and are populated."""
    expected_files = [
        SQL_DIR / "schema" / "01_staging_schema.sql",
        SQL_DIR / "schema" / "02_dimensional_schema.sql",
        SQL_DIR / "schema" / "03_load_dimensions_and_facts.sql",
        SQL_DIR / "views" / "01_analytical_views.sql",
        SQL_DIR / "analysis" / "01_kpi_sales_and_orders.sql",
        SQL_DIR / "analysis" / "02_delivery_operations_and_sla.sql",
        SQL_DIR / "analysis" / "03_customer_intelligence_and_rfm.sql",
        SQL_DIR / "analysis" / "04_operational_quality_and_reconciliation.sql",
    ]

    for sql_file in expected_files:
        assert sql_file.is_file(), f"Missing required SQL file: {sql_file.relative_to(PROJECT_ROOT)}"
        content = sql_file.read_text(encoding="utf-8")
        assert len(content.strip()) > 100, f"SQL file appears empty or incomplete: {sql_file.name}"


def test_sql_analysis_files_contain_required_features():
    """Verify required window functions, CTEs, and anti-fan-out clauses exist in analysis scripts."""
    sales_sql = (SQL_DIR / "analysis" / "01_kpi_sales_and_orders.sql").read_text(encoding="utf-8")
    assert "WITH" in sales_sql
    assert "LAG(" in sales_sql
    assert "DENSE_RANK(" in sales_sql
    assert "NTILE(" in sales_sql

    delivery_sql = (SQL_DIR / "analysis" / "02_delivery_operations_and_sla.sql").read_text(encoding="utf-8")
    assert "is_eligible_for_sla" in delivery_sql
    assert "RANK(" in delivery_sql

    reconcile_sql = (SQL_DIR / "analysis" / "04_operational_quality_and_reconciliation.sql").read_text(encoding="utf-8")
    assert "naive_fanout_join" in reconcile_sql
    assert "controlled_grain_aggregation" in reconcile_sql
    assert "0.00" in reconcile_sql  # Zero-value retention check


# ------------------------------------------------------------------------------
# 2. Connection & Security Masking
# ------------------------------------------------------------------------------
def test_mask_connection_url():
    """Verify password masking never leaks secrets in logs or reports."""
    url_with_pass = "postgresql+psycopg2://admin:super_secret_password123@localhost:5432/commercelens_db"
    masked = mask_connection_url(url_with_pass)
    assert "super_secret_password123" not in masked
    assert "admin:***@localhost:5432/commercelens_db" in masked

    # URL without password
    url_without_pass = "postgresql+psycopg2://postgres@localhost:5432/db"
    assert mask_connection_url(url_without_pass) == url_without_pass


def test_check_connection_graceful_failure_when_server_offline():
    """Verify check_connection catches unreachable server or missing driver gracefully without throwing."""
    test_url = "postgresql+psycopg2://dummy:supersecret123@127.0.0.1:54321/nonexistent"
    is_connected, msg = check_connection(test_url)
    assert is_connected is False
    assert "supersecret123" not in msg
    assert "dummy:***@" in msg  # password masked
    assert "54321" in msg


# ------------------------------------------------------------------------------
# 3. Cleaned Data Parquet/CSV Grain & Row Count Validation
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "file_base, expected_rows",
    [
        ("cleaned_orders", 99441),
        ("cleaned_order_items", 112650),
        ("cleaned_order_payments", 103886),
        ("cleaned_order_reviews", 99224),
        ("cleaned_customers", 99441),
        ("cleaned_sellers", 3095),
        ("cleaned_products", 32951),
        ("cleaned_geolocation_centroids", 19010),
        ("cleaned_category_translation", 71),
    ],
)
def test_cleaned_datasets_exist_with_exact_row_counts(file_base: str, expected_rows: int):
    """Verify that every cleaned dataset exists and matches the verified historical row count."""
    df = load_processed_dataframe(PROCESSED_DATA_DIR, file_base)
    assert len(df) == expected_rows, (
        f"Row count mismatch for {file_base}: expected {expected_rows}, got {len(df)}"
    )


def test_primary_and_compound_keys_are_unique():
    """Verify primary and compound business keys on actual cleaned datasets."""
    customers = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_customers")
    assert customers["customer_id"].is_unique, "customer_id must be unique"

    sellers = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_sellers")
    assert sellers["seller_id"].is_unique, "seller_id must be unique"

    products = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_products")
    assert products["product_id"].is_unique, "product_id must be unique"

    geo = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_geolocation_centroids")
    assert geo["zip_code_prefix"].is_unique, "zip_code_prefix must be unique (1 centroid per prefix)"

    orders = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_orders")
    assert orders["order_id"].is_unique, "order_id must be unique"

    items = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_order_items")
    assert not items.duplicated(subset=["order_id", "order_item_id"]).any(), (
        "(order_id, order_item_id) must be unique"
    )

    payments = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_order_payments")
    assert not payments.duplicated(subset=["order_id", "payment_sequential"]).any(), (
        "(order_id, payment_sequential) must be unique"
    )

    # Compound key for reviews
    reviews = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_order_reviews")
    # Verify review_id alone has duplicates (789 groups)
    assert reviews["review_id"].duplicated().any(), "review_id alone must have duplicates in raw Olist"
    # Verify compound key (review_id, order_id) is 100% unique
    assert not reviews.duplicated(subset=["review_id", "order_id"]).any(), (
        "Compound key (review_id, order_id) must be 100% unique"
    )


# ------------------------------------------------------------------------------
# 4. Strict Business Rules on Real Data
# ------------------------------------------------------------------------------
def test_zero_value_voucher_payments_strictly_retained():
    """Verify that exactly 9 zero-value payments exist in cleaned_order_payments (6 voucher, 3 not_defined)."""
    payments = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_order_payments")
    zero_payments = payments[payments["payment_value"] == 0.0]
    assert len(zero_payments) == 9, (
        f"Expected exactly 9 zero-value payments retained, found {len(zero_payments)}"
    )
    assert set(zero_payments["payment_type"]) == {"voucher", "not_defined"}, (
        "Zero-value payments must be 6 vouchers and 3 not_defined records"
    )


def test_sla_denominator_excludes_eight_delivered_orders():
    """
    Verify that exactly 8 orders have status 'delivered' but NULL customer delivery date,
    and must be excluded from SLA compliance on-time/late denominators.
    """
    orders = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_orders")
    delivered_orders = orders[orders["order_status"] == "delivered"]
    assert len(delivered_orders) == 96478

    missing_del_timestamp = delivered_orders[delivered_orders["order_delivered_customer_date"].isna()]
    assert len(missing_del_timestamp) == 8, (
        f"Expected exactly 8 delivered orders missing delivery timestamps, found {len(missing_del_timestamp)}"
    )

    # Valid SLA-eligible cohort is 96,478 - 8 = 96,470
    valid_sla_cohort = delivered_orders[delivered_orders["order_delivered_customer_date"].notna()]
    assert len(valid_sla_cohort) == 96470


def test_category_provenance_and_null_preservation():
    """
    Verify that 610 missing categories remain null, and translations handle known additions.
    """
    products = load_processed_dataframe(PROCESSED_DATA_DIR, "cleaned_products")
    null_cats = products["product_category_name"].isna().sum()
    assert null_cats == 610, f"Expected exactly 610 missing categories preserved, found {null_cats}"

    # Overridden categories present
    assert "pc_gamer" in products["product_category_name"].values
    assert "portateis_cozinha_e_preparadores_de_alimentos" in products["product_category_name"].values


# ------------------------------------------------------------------------------
# 5. Anti-Fan-Out & Reconciliation Test Fixture (In-Memory Relational Engine)
# ------------------------------------------------------------------------------
@pytest.fixture
def memory_db_fixture():
    """
    Sets up an in-memory SQLite database mimicking the Kimball Star Schema
    with synthetic multi-item and multi-payment orders to test anti-fan-out math.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE fact_orders (
                order_id TEXT PRIMARY KEY,
                is_delivered BOOLEAN,
                is_late BOOLEAN,
                is_eligible_for_sla BOOLEAN,
                order_delivered_customer_date TEXT,
                delivery_lead_time_days REAL,
                carrier_transit_days REAL,
                seller_dispatch_days REAL,
                sla_variance_days REAL,
                total_items_count INTEGER,
                total_item_merchandise_value REAL,
                total_freight_value REAL,
                total_payment_value REAL,
                payment_slices_count INTEGER
            );
        """))
        conn.execute(text("""
            CREATE TABLE fact_order_items (
                order_id TEXT,
                order_item_id INTEGER,
                price REAL,
                freight_value REAL,
                PRIMARY KEY (order_id, order_item_id)
            );
        """))
        conn.execute(text("""
            CREATE TABLE fact_payments (
                order_id TEXT,
                payment_sequential INTEGER,
                payment_type TEXT,
                payment_value REAL,
                PRIMARY KEY (order_id, payment_sequential)
            );
        """))

        # Order 1: Simple (1 item, 1 payment)
        conn.execute(text("""
            INSERT INTO fact_orders VALUES 
            ('ORD_1', 1, 0, 1, '2018-01-10', 5.0, 3.0, 2.0, 10.0, 1, 100.0, 20.0, 120.0, 1);
        """))
        conn.execute(text("INSERT INTO fact_order_items VALUES ('ORD_1', 1, 100.0, 20.0);"))
        conn.execute(text("INSERT INTO fact_payments VALUES ('ORD_1', 1, 'credit_card', 120.0);"))

        # Order 2: Complex (2 items, 2 payments) -> High risk of Cartesian explosion (2x2 = 4)
        conn.execute(text("""
            INSERT INTO fact_orders VALUES 
            ('ORD_2', 1, 1, 1, '2018-02-15', 15.0, 10.0, 5.0, -2.0, 2, 120.0, 30.0, 150.0, 2);
        """))
        conn.execute(text("INSERT INTO fact_order_items VALUES ('ORD_2', 1, 50.0, 15.0);"))
        conn.execute(text("INSERT INTO fact_order_items VALUES ('ORD_2', 2, 70.0, 15.0);"))
        conn.execute(text("INSERT INTO fact_payments VALUES ('ORD_2', 1, 'voucher', 50.0);"))
        conn.execute(text("INSERT INTO fact_payments VALUES ('ORD_2', 2, 'credit_card', 100.0);"))

        # Order 3: Delivered but missing customer delivery date (The 8-order anomaly)
        conn.execute(text("""
            INSERT INTO fact_orders VALUES 
            ('ORD_3_MISSING', 1, 0, 0, NULL, NULL, NULL, NULL, NULL, 1, 80.0, 10.0, 90.0, 1);
        """))
        conn.execute(text("INSERT INTO fact_order_items VALUES ('ORD_3_MISSING', 1, 80.0, 10.0);"))
        conn.execute(text("INSERT INTO fact_payments VALUES ('ORD_3_MISSING', 1, 'credit_card', 90.0);"))

    return engine


def test_anti_fanout_mathematical_proof(memory_db_fixture):
    """
    Demonstrate that naive join doubles the merchandise and payment totals on Order 2,
    while CTE pre-aggregation preserves exact financial totals.
    """
    engine = memory_db_fixture
    impact = demonstrate_anti_fanout_impact(engine, "ORD_2")

    # Order 2 has 2 items and 2 payments
    assert impact["items_count"] == 2
    assert impact["payments_count"] == 2
    assert impact["cartesian_rows"] == 4  # 2 x 2 Cartesian product

    # Naive join doubles the sums (each item summed twice, each payment summed twice)
    assert impact["correct_merchandise_value"] == 120.0
    assert impact["naive_merchandise_value"] == 240.0  # 100% inflation error!

    assert impact["correct_payment_value"] == 150.0
    assert impact["naive_payment_value"] == 300.0  # 100% inflation error!


def test_financial_reconciliation_zero_variance(memory_db_fixture):
    """Verify that pre-aggregated fact_orders equals line facts with 0.00 variance."""
    engine = memory_db_fixture
    reconciliation = calculate_reconciliation_audit(engine)

    assert len(reconciliation) == 3
    for _, row in reconciliation.iterrows():
        assert row["variance"] == 0.0, f"Variance detected in {row['metric_name']}: {row['variance']}"


def test_delivery_sla_denominator_isolation(memory_db_fixture):
    """
    Verify that calculate_delivery_sla_summary strictly isolates the missing timestamp order:
    - ORD_3_MISSING is delivered but excluded from sla_eligible_delivered_orders.
    - Total delivered = 3, Eligible delivered = 2.
    """
    engine = memory_db_fixture
    sla = calculate_delivery_sla_summary(engine)

    assert sla["total_orders"] == 3
    assert sla["total_delivered_orders"] == 3
    assert sla["sla_eligible_delivered_orders"] == 2
    assert sla["delivered_missing_timestamp_orders"] == 1

    # 1 on-time, 1 late out of 2 eligible
    assert sla["on_time_orders_count"] == 1
    assert sla["late_orders_count"] == 1
    assert sla["on_time_delivery_rate_pct"] == 50.0
    assert sla["late_delivery_rate_pct"] == 50.0
