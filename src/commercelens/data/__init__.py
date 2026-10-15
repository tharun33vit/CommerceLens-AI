"""
Data Engineering, Ingestion, and Quality Audit Module for CommerceLens AI.
"""

from commercelens.data.schema import (
    CANDIDATE_PRIMARY_KEYS,
    DATETIME_COLUMNS,
    EXPECTED_RAW_FILES,
    EXPECTED_RELATIONSHIPS,
    FindingSeverity,
    QualityFinding,
    TableInventoryItem,
)
from commercelens.data.ingest import (
    discover_raw_files,
    generate_table_inventory,
    load_raw_dataset_inventory,
    read_raw_csv,
    RawDataMissingError,
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
    clean_all_datasets,
    clean_customers,
    clean_geolocation,
    clean_order_items,
    clean_orders,
    clean_products,
    clean_sellers,
    save_processed_datasets,
)
from commercelens.data.report import (
    export_findings_json,
    export_inventory_json,
    export_missing_values_csv,
    export_relationship_validation_json,
    generate_all_reports,
    generate_markdown_quality_report,
)
from commercelens.data.pipeline import run_phase1_pipeline

__all__ = [
    "CANDIDATE_PRIMARY_KEYS",
    "DATETIME_COLUMNS",
    "EXPECTED_RAW_FILES",
    "EXPECTED_RELATIONSHIPS",
    "FindingSeverity",
    "QualityFinding",
    "TableInventoryItem",
    "discover_raw_files",
    "generate_table_inventory",
    "load_raw_dataset_inventory",
    "read_raw_csv",
    "RawDataMissingError",
    "audit_business_rule_anomalies",
    "audit_duplicates",
    "audit_missing_values",
    "execute_comprehensive_audit",
    "validate_candidate_keys",
    "validate_relationships",
    "clean_all_datasets",
    "clean_customers",
    "clean_geolocation",
    "clean_order_items",
    "clean_orders",
    "clean_products",
    "clean_sellers",
    "save_processed_datasets",
    "export_findings_json",
    "export_inventory_json",
    "export_missing_values_csv",
    "export_relationship_validation_json",
    "generate_all_reports",
    "generate_markdown_quality_report",
    "run_phase1_pipeline",
]
