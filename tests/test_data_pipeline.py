"""
Automated unit tests for Phase 1 Data Ingestion, Profiling and Quality Audit.
Uses synthetic isolated fixtures (tmp_path) to verify data processing logic.
"""

import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest

from commercelens.data.schema import EXPECTED_RAW_FILES
from commercelens.data.ingest import (
    discover_raw_files,
    load_raw_dataset_inventory,
    read_raw_csv,
)
from commercelens.data.audit import (
    audit_business_rule_anomalies,
    audit_duplicates,
    audit_missing_values,
    execute_comprehensive_audit,
    validate_candidate_keys,
    validate_relationships,
)
from commercelens.data.clean import (
    clean_customers,
    clean_geolocation,
    clean_orders,
    clean_products,
    clean_sellers,
    save_processed_datasets,
)
from commercelens.data.report import generate_all_reports
from commercelens.data.pipeline import run_phase1_pipeline


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def synthetic_raw_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with synthetic mock CSVs for all 9 tables."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # 1. orders
    orders_df = pd.DataFrame({
        "order_id": ["ord_1", "ord_2", "ord_3"],
        "customer_id": ["cust_1", "cust_2", "cust_3"],
        "order_status": ["delivered", "delivered", "canceled"],
        "order_purchase_timestamp": ["2018-01-01 10:00:00", "2018-01-02 11:00:00", "2018-01-03 12:00:00"],
        "order_approved_at": ["2018-01-01 10:15:00", "2018-01-02 11:30:00", None],
        "order_delivered_carrier_date": ["2018-01-03 08:00:00", "2018-01-04 09:00:00", None],
        "order_delivered_customer_date": ["2018-01-08 14:00:00", "2018-01-15 16:00:00", None],
        "order_estimated_delivery_date": ["2018-01-10 00:00:00", "2018-01-12 00:00:00", "2018-01-15 00:00:00"],
    })
    orders_df.to_csv(raw_dir / "olist_orders_dataset.csv", index=False)

    # 2. order_items
    items_df = pd.DataFrame({
        "order_id": ["ord_1", "ord_1", "ord_2"],
        "order_item_id": [1, 2, 1],
        "product_id": ["prod_1", "prod_2", "prod_1"],
        "seller_id": ["sell_1", "sell_2", "sell_1"],
        "shipping_limit_date": ["2018-01-05 00:00:00", "2018-01-05 00:00:00", "2018-01-06 00:00:00"],
        "price": [100.0, 50.0, 200.0],
        "freight_value": [15.0, 10.0, 25.0],
    })
    items_df.to_csv(raw_dir / "olist_order_items_dataset.csv", index=False)

    # 3. order_payments
    pay_df = pd.DataFrame({
        "order_id": ["ord_1", "ord_1", "ord_2"],
        "payment_sequential": [1, 2, 1],
        "payment_type": ["credit_card", "voucher", "boleto"],
        "payment_installments": [2, 1, 1],
        "payment_value": [150.0, 25.0, 225.0],
    })
    pay_df.to_csv(raw_dir / "olist_order_payments_dataset.csv", index=False)

    # 4. order_reviews
    rev_df = pd.DataFrame({
        "review_id": ["rev_1", "rev_2"],
        "order_id": ["ord_1", "ord_2"],
        "review_score": [5, 1],
        "review_comment_title": ["Otimo", "Atrasou"],
        "review_comment_message": ["Chegou muito rapido", "Demorou demais para entregar"],
        "review_creation_date": ["2018-01-09 00:00:00", "2018-01-16 00:00:00"],
        "review_answer_timestamp": ["2018-01-10 10:00:00", "2018-01-17 11:00:00"],
    })
    rev_df.to_csv(raw_dir / "olist_order_reviews_dataset.csv", index=False)

    # 5. customers
    cust_df = pd.DataFrame({
        "customer_id": ["cust_1", "cust_2", "cust_3"],
        "customer_unique_id": ["uniq_1", "uniq_2", "uniq_1"],
        "customer_zip_code_prefix": [1234, 56789, 1234],
        "customer_city": ["Sao Paulo", "Rio de Janeiro", "Sao Paulo"],
        "customer_state": ["sp", "rj", "sp"],
    })
    cust_df.to_csv(raw_dir / "olist_customers_dataset.csv", index=False)

    # 6. sellers
    sell_df = pd.DataFrame({
        "seller_id": ["sell_1", "sell_2"],
        "seller_zip_code_prefix": [1000, 20000],
        "seller_city": ["Sao Paulo", "Curitiba"],
        "seller_state": ["sp", "pr"],
    })
    sell_df.to_csv(raw_dir / "olist_sellers_dataset.csv", index=False)

    # 7. products
    prod_df = pd.DataFrame({
        "product_id": ["prod_1", "prod_2"],
        "product_category_name": ["beleza_saude", "cama_mesa_banho"],
        "product_name_lenght": [50, 40],
        "product_description_lenght": [300, 200],
        "product_photos_qty": [2, 1],
        "product_weight_g": [500, 800],
        "product_length_cm": [20, 30],
        "product_height_cm": [10, 15],
        "product_width_cm": [15, 20],
    })
    prod_df.to_csv(raw_dir / "olist_products_dataset.csv", index=False)

    # 8. geolocation
    geo_df = pd.DataFrame({
        "geolocation_zip_code_prefix": [1234, 1234, 56789],
        "geolocation_lat": [-23.5505, -23.5510, -22.9068],
        "geolocation_lng": [-46.6333, -46.6340, -43.1729],
        "geolocation_city": ["sao paulo", "sao paulo", "rio de janeiro"],
        "geolocation_state": ["SP", "SP", "RJ"],
    })
    geo_df.to_csv(raw_dir / "olist_geolocation_dataset.csv", index=False)

    # 9. category translation
    trans_df = pd.DataFrame({
        "product_category_name": ["beleza_saude", "cama_mesa_banho"],
        "product_category_name_english": ["health_beauty", "bed_bath_table"],
    })
    trans_df.to_csv(raw_dir / "product_category_name_translation.csv", index=False)

    return raw_dir


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
def test_missing_required_files(tmp_path: Path):
    """Verify that discovery detects missing files in an empty or partial directory."""
    empty_dir = tmp_path / "empty_raw"
    empty_dir.mkdir()

    found, missing = discover_raw_files(empty_dir)
    assert len(found) == 0
    assert len(missing) == 9
    assert "olist_orders_dataset.csv" in missing

    # Test load_raw_dataset_inventory halts
    tables, inv, missing_files = load_raw_dataset_inventory(empty_dir, require_all=True)
    assert len(tables) == 0
    assert len(inv) == 0
    assert len(missing_files) == 9


def test_successful_csv_discovery_and_loading(synthetic_raw_dir: Path):
    """Verify that all 9 expected files are discovered and loaded when present."""
    found, missing = discover_raw_files(synthetic_raw_dir)
    assert len(missing) == 0
    assert len(found) == 9

    tables, inventory, missing_list = load_raw_dataset_inventory(synthetic_raw_dir, require_all=True)
    assert len(missing_list) == 0
    assert len(tables) == 9
    assert len(inventory) == 9
    assert "orders" in tables
    assert len(tables["orders"]) == 3


def test_missing_value_profiling():
    """Verify missing-value counts and percentages calculation."""
    df = pd.DataFrame({
        "col_a": [1, None, 3, None, 5],  # 2 nulls = 40.0%
        "col_b": ["a", "b", "c", "d", "e"],  # 0 nulls = 0.0%
    })
    stats = audit_missing_values({"test_table": df})
    assert len(stats) == 2

    stat_a = next(s for s in stats if s.column_name == "col_a")
    assert stat_a.missing_count == 2
    assert stat_a.missing_percentage == 40.0
    assert stat_a.total_rows == 5

    stat_b = next(s for s in stats if s.column_name == "col_b")
    assert stat_b.missing_count == 0
    assert stat_b.missing_percentage == 0.0


def test_duplicate_detection():
    """Verify exact complete duplicate detection."""
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "val": ["x", "y", "y", "z"],
    })
    stats = audit_duplicates({"test_table": df})
    assert len(stats) == 1
    assert stats[0].complete_duplicates_count == 1
    assert stats[0].complete_duplicates_percentage == 25.0


def test_candidate_key_validation():
    """Verify primary key uniqueness and nullity checks."""
    valid_df = pd.DataFrame({"order_id": ["o1", "o2", "o3"], "val": [10, 20, 30]})
    invalid_df = pd.DataFrame({"order_id": ["o1", "o1", None], "val": [10, 20, 30]})

    stats_valid = validate_candidate_keys({"orders": valid_df})
    key_v = next(k for k in stats_valid if k.table_name == "orders")
    assert key_v.is_valid_pk is True
    assert key_v.duplicate_key_count == 0
    assert key_v.null_key_count == 0

    stats_invalid = validate_candidate_keys({"orders": invalid_df})
    key_inv = next(k for k in stats_invalid if k.table_name == "orders")
    assert key_inv.is_valid_pk is False
    assert key_inv.duplicate_key_count > 0 or key_inv.null_key_count > 0


def test_foreign_key_integrity_checks():
    """Verify referential integrity computation between parent and child tables."""
    parents = pd.DataFrame({"order_id": ["o1", "o2"]})
    # Child has 2 valid, 1 orphan ('o3')
    children = pd.DataFrame({"order_id": ["o1", "o2", "o3"], "order_item_id": [1, 1, 1]})

    tables = {"orders": parents, "order_items": children}
    stats = validate_relationships(tables)

    rel = next(r for r in stats if r.relationship_name == "order_items_to_orders")
    assert rel.child_total_records == 3
    assert rel.unmatched_child_records == 1
    assert rel.unmatched_child_keys == 1
    assert rel.is_clean is False
    assert round(rel.referential_integrity_percentage, 1) == 66.7


def test_invalid_date_handling(tmp_path: Path):
    """Verify safe handling of invalid date strings and chronological anomaly detection."""
    csv_file = tmp_path / "bad_dates.csv"
    csv_file.write_text(
        "order_id,order_purchase_timestamp,order_delivered_customer_date,order_estimated_delivery_date,order_status\n"
        "o1,not-a-date,2018-01-05 00:00:00,2018-01-10 00:00:00,delivered\n"
        "o2,2018-01-10 00:00:00,2018-01-05 00:00:00,2018-01-12 00:00:00,delivered\n"  # Delivered before purchase
    )

    df, parsed = read_raw_csv(csv_file, table_name="orders", parse_dates=True)
    # The invalid string should safely become NaT without raising exception
    assert pd.isna(df.loc[0, "order_purchase_timestamp"])
    assert pd.notna(df.loc[1, "order_purchase_timestamp"])

    cleaned, metrics = clean_orders(df)
    # o2 should have chronological anomaly flagged
    assert cleaned.loc[1, "has_timestamp_anomaly"] == True


def test_report_generation(synthetic_raw_dir: Path, tmp_path: Path):
    """Verify that all 5 report artifacts are written and contain expected sections."""
    tables, inventory, _ = load_raw_dataset_inventory(synthetic_raw_dir)
    audit = execute_comprehensive_audit(tables)

    rep_dir = tmp_path / "reports"
    reports = generate_all_reports(inventory, audit, rep_dir)

    for rep_name, rep_path in reports.items():
        assert rep_path.exists(), f"Report file missing: {rep_name}"
        assert rep_path.stat().st_size > 0, f"Report file empty: {rep_name}"

    # Verify JSON structure
    with open(reports["file_inventory_json"], "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    assert len(inv_data) == 9

    # Verify Markdown report contains header
    md_content = reports["markdown_report"].read_text(encoding="utf-8")
    assert "CommerceLens AI — Data Ingestion & Quality Audit Report" in md_content
    assert "Executive Summary & File Inventory" in md_content


def test_preservation_of_raw_files(synthetic_raw_dir: Path):
    """Verify that running ingestion, audit, and cleaning never modifies raw CSV files."""
    orders_csv = synthetic_raw_dir / "olist_orders_dataset.csv"
    initial_hash = hashlib.sha256(orders_csv.read_bytes()).hexdigest()

    tables, inventory, _ = load_raw_dataset_inventory(synthetic_raw_dir)
    audit = execute_comprehensive_audit(tables)
    cleaned, _ = clean_orders(tables["orders"])

    post_hash = hashlib.sha256(orders_csv.read_bytes()).hexdigest()
    assert initial_hash == post_hash, "Raw CSV file was modified during processing!"


def test_full_pipeline_halt_on_missing_files(tmp_path: Path):
    """Verify that run_phase1_pipeline cleanly halts when raw files are absent."""
    empty_raw = tmp_path / "raw"
    empty_raw.mkdir()
    proc_dir = tmp_path / "processed"
    rep_dir = tmp_path / "reports"

    result = run_phase1_pipeline(empty_raw, proc_dir, rep_dir)
    assert result["status"] == "HALTED_MISSING_RAW_DATA"
    assert result["missing_files_count"] == 9
    assert (rep_dir / "data_quality" / "pipeline_status.json").exists()


def test_delivery_date_reconciliation():
    """
    Verify that delivery timestamp findings reconcile 100% of missing timestamps
    across all order statuses, preventing unexplained discrepancies.
    """
    # Synthetic orders table with various statuses missing timestamps
    orders_df = pd.DataFrame({
        "order_id": [f"ord_{i}" for i in range(10)],
        "order_status": [
            "delivered",    # ord_0: delivered with missing timestamp (anomaly)
            "shipped",      # ord_1: non-delivered missing timestamp
            "canceled",     # ord_2: non-delivered missing timestamp
            "unavailable",  # ord_3: non-delivered missing timestamp
            "invoiced",     # ord_4: non-delivered missing timestamp
            "processing",   # ord_5: non-delivered missing timestamp
            "created",      # ord_6: non-delivered missing timestamp
            "approved",     # ord_7: non-delivered missing timestamp
            "delivered",    # ord_8: delivered with timestamp (normal)
            "delivered",    # ord_9: delivered with timestamp (normal)
        ],
        "order_purchase_timestamp": pd.date_range("2018-01-01", periods=10, freq="D"),
        "order_delivered_customer_date": [
            None, None, None, None, None, None, None, None,
            pd.Timestamp("2018-01-10"), pd.Timestamp("2018-01-11"),
        ],
        "order_estimated_delivery_date": pd.date_range("2018-01-15", periods=10, freq="D"),
    })

    findings = audit_business_rule_anomalies({"orders": orders_df})
    total_null = int(orders_df["order_delivered_customer_date"].isnull().sum())
    assert total_null == 8

    stat_01 = next((f for f in findings if f.finding_id == "ORD_STAT_01"), None)
    stat_02 = next((f for f in findings if f.finding_id == "ORD_STAT_02"), None)

    assert stat_01 is not None, "ORD_STAT_01 (delivered missing timestamp) must be reported"
    assert stat_02 is not None, "ORD_STAT_02 (non-delivered missing timestamp) must be reported"

    # Extract counts from evidence strings
    assert "1 orders marked as 'delivered'" in stat_01.evidence
    assert "7 orders across all non-delivered statuses" in stat_02.evidence
    # 1 delivered + 7 non-delivered = 8 total nulls (100% reconciled)
    assert "1 delivered + 7 non-delivered = 8 total missing" in stat_02.evidence


def test_duplicate_metric_definitions():
    """
    Verify the mathematical definitions and arithmetic separation between:
    - duplicate_key_groups: distinct candidate-key values appearing > 1 time
    - excess_duplicate_rows: total rows - distinct candidate keys
    """
    # Key values: A (3 rows), B (2 rows), C (1 row) -> Total 6 rows, 3 distinct keys
    df = pd.DataFrame({
        "order_id": ["A", "A", "A", "B", "B", "C"],
        "val": [1, 2, 3, 4, 5, 6],
    })

    stats = validate_candidate_keys({"orders": df})
    key_stat = next(k for k in stats if k.table_name == "orders")

    assert key_stat.total_rows == 6
    assert key_stat.distinct_key_count == 3
    # Two key groups ('A' and 'B') have count > 1
    assert key_stat.duplicate_key_groups == 2
    # Excess rows = 6 - 3 = 3
    assert key_stat.excess_duplicate_rows == 3
    # Verify exact arithmetic
    assert key_stat.excess_duplicate_rows == (key_stat.total_rows - key_stat.distinct_key_count)


def test_category_mapping_gaps_distinction():
    """
    Verify that category audit and cleaning strictly distinguish between:
    1. Products with null product_category_name
    2. Products with non-null category lacking translation
    3. Distinct untranslated category names
    and that no synthetic categories (e.g. 'unclassified') are invented.
    """
    prod_df = pd.DataFrame({
        "product_id": ["p1", "p2", "p3", "p4", "p5"],
        "product_category_name": [
            None,                                            # 1. Null category
            "beleza_saude",                                  # 2. Translated category
            "pc_gamer",                                      # 3. Non-null untranslated
            "portateis_cozinha_e_preparadores_de_alimentos", # 4. Non-null untranslated
            "pc_gamer",                                      # 5. Non-null untranslated (second product)
        ],
    })
    trans_df = pd.DataFrame({
        "product_category_name": ["beleza_saude"],
        "product_category_name_english": ["health_beauty"],
    })

    findings = audit_business_rule_anomalies({
        "products": prod_df,
        "category_translation": trans_df,
    })

    cat_finding = next((f for f in findings if f.finding_id == "PROD_CAT_01"), None)
    assert cat_finding is not None
    assert "1 products have NULL product_category_name" in cat_finding.evidence
    assert "3 products have non-null categories lacking an English translation" in cat_finding.evidence
    assert "across 2 distinct categories" in cat_finding.evidence
    assert "'pc_gamer' (2 products)" in cat_finding.evidence
    assert "'portateis_cozinha_e_preparadores_de_alimentos' (1 products)" in cat_finding.evidence

    # Verify cleaning preserves nulls without inventing placeholder values
    cleaned_prod, clean_metrics = clean_products(prod_df, trans_df)
    assert clean_metrics["products_with_null_category"] == 1
    assert clean_metrics["products_with_untranslated_category"] == 3
    assert set(clean_metrics["distinct_untranslated_categories"]) == {
        "pc_gamer",
        "portateis_cozinha_e_preparadores_de_alimentos",
    }

    # Crucial assertion: no 'unclassified' or placeholder strings created
    assert pd.isna(cleaned_prod.loc[0, "product_category_name_english"])
    assert cleaned_prod.loc[1, "product_category_name_english"] == "health_beauty"
    assert pd.isna(cleaned_prod.loc[2, "product_category_name_english"])
    assert pd.isna(cleaned_prod.loc[3, "product_category_name_english"])
    assert pd.isna(cleaned_prod.loc[4, "product_category_name_english"])

