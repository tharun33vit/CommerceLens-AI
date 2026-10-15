"""
Analytics & Relational Modeling Module
======================================
Contains SQL query runners, KPI calculators, metrics aggregation logic,
database connection management, and loading pipelines for CommerceLens AI.
"""

from commercelens.analytics.db import (
    check_connection,
    create_db_engine,
    ensure_database_exists,
    execute_sql_file,
    get_database_url,
    mask_connection_url,
)
from commercelens.analytics.loader import (
    EXPECTED_STAGING_ROW_COUNTS,
    LoadResult,
    load_processed_dataframe,
    load_staging_tables,
    run_full_database_pipeline,
)
from commercelens.analytics.kpis import (
    calculate_delivery_sla_summary,
    calculate_reconciliation_audit,
    calculate_sales_kpis,
    demonstrate_anti_fanout_impact,
)

__all__ = [
    "check_connection",
    "create_db_engine",
    "ensure_database_exists",
    "execute_sql_file",
    "get_database_url",
    "mask_connection_url",
    "EXPECTED_STAGING_ROW_COUNTS",
    "LoadResult",
    "load_processed_dataframe",
    "load_staging_tables",
    "run_full_database_pipeline",
    "calculate_delivery_sla_summary",
    "calculate_reconciliation_audit",
    "calculate_sales_kpis",
    "demonstrate_anti_fanout_impact",
]
