"""
Data Loader & Pipeline Execution Utility for PostgreSQL Analytics.

Loads cleaned datasets from data/processed/ into PostgreSQL staging tables,
executes dimensional transformation pipelines, and performs automated reconciliation.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from commercelens.analytics.db import create_db_engine, execute_sql_file, mask_connection_url

logger = logging.getLogger(__name__)

# Mapping from staging table name to processed file base name
STAGING_FILE_MAPPING: Dict[str, str] = {
    "stg_customers": "cleaned_customers",
    "stg_sellers": "cleaned_sellers",
    "stg_category_translation": "cleaned_category_translation",
    "stg_products": "cleaned_products",
    "stg_geolocation_centroids": "cleaned_geolocation_centroids",
    "stg_orders": "cleaned_orders",
    "stg_order_items": "cleaned_order_items",
    "stg_order_payments": "cleaned_order_payments",
    "stg_order_reviews": "cleaned_order_reviews",
}

EXPECTED_STAGING_ROW_COUNTS: Dict[str, int] = {
    "stg_customers": 99441,
    "stg_sellers": 3095,
    "stg_category_translation": 71,
    "stg_products": 32951,
    "stg_geolocation_centroids": 19010,
    "stg_orders": 99441,
    "stg_order_items": 112650,
    "stg_order_payments": 103886,
    "stg_order_reviews": 99224,
}


@dataclass
class LoadResult:
    """Summary of data loading operation."""
    success: bool
    staging_counts: Dict[str, int]
    dimensional_counts: Dict[str, int]
    discrepancies: List[str]
    message: str


def load_processed_dataframe(processed_dir: Path, base_filename: str) -> pd.DataFrame:
    """
    Load a processed dataset, preferring Parquet for speed and fallback to CSV.
    """
    parquet_path = processed_dir / f"{base_filename}.parquet"
    csv_path = processed_dir / f"{base_filename}.csv"

    if parquet_path.is_file():
        return pd.read_parquet(parquet_path)
    elif csv_path.is_file():
        return pd.read_csv(csv_path)
    else:
        raise FileNotFoundError(
            f"Could not find processed dataset for '{base_filename}' at {processed_dir}. "
            f"Expected either {parquet_path.name} or {csv_path.name}."
        )


def load_staging_tables(
    engine: Engine,
    processed_dir: Path,
    batch_size: int = 10000,
) -> Dict[str, int]:
    """
    Load all 9 processed datasets into their corresponding stg_* tables.
    Uses safe chunked insertion and reports loaded row counts.
    """
    loaded_counts: Dict[str, int] = {}
    processed_path = Path(processed_dir).resolve()

    for table_name, file_base in STAGING_FILE_MAPPING.items():
        df = load_processed_dataframe(processed_path, file_base)
        
        # Clean boolean columns if loading to SQLite/PostgreSQL
        for col in df.select_dtypes(include=["bool"]).columns:
            df[col] = df[col].astype(bool)

        logger.info(f"Loading {len(df):,} rows into {table_name}...")
        
        # In staging layer, replace existing contents to prevent duplicated loads on reruns
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="append",
            index=False,
            chunksize=batch_size,
            method="multi",
        )
        loaded_counts[table_name] = len(df)

    return loaded_counts


def run_full_database_pipeline(
    engine: Engine,
    sql_dir: Path,
    processed_dir: Path,
) -> LoadResult:
    """
    Execute full end-to-end database pipeline:
    1. Run 01_staging_schema.sql (Create staging tables)
    2. Load processed datasets into stg_*
    3. Run 02_dimensional_schema.sql (Create Kimball star schema)
    4. Run 03_load_dimensions_and_facts.sql (Populate dims & facts)
    5. Run 01_analytical_views.sql (Create views)
    6. Validate row counts and integrity constraints.
    """
    sql_path = Path(sql_dir).resolve()
    processed_path = Path(processed_dir).resolve()
    discrepancies: List[str] = []

    logger.info(f"Starting database pipeline on {mask_connection_url(str(engine.url))}...")

    # 1. Staging Schema DDL
    execute_sql_file(engine, sql_path / "schema" / "01_staging_schema.sql")

    # 2. Ingest into staging
    staging_counts = load_staging_tables(engine, processed_path)

    # Validate staging counts
    for table, expected in EXPECTED_STAGING_ROW_COUNTS.items():
        actual = staging_counts.get(table, 0)
        if actual != expected:
            discrepancies.append(
                f"Staging count mismatch for {table}: expected {expected}, got {actual}"
            )

    # 3. Dimensional Schema DDL
    execute_sql_file(engine, sql_path / "schema" / "02_dimensional_schema.sql")

    # 4. ELT Transform into Dimensions & Facts
    execute_sql_file(engine, sql_path / "schema" / "03_load_dimensions_and_facts.sql")

    # 5. Semantic Views DDL
    execute_sql_file(engine, sql_path / "views" / "01_analytical_views.sql")

    # 6. Query dimensional counts
    dimensional_counts: Dict[str, int] = {}
    dim_fact_tables = [
        "dim_customers",
        "dim_sellers",
        "dim_products",
        "dim_geography",
        "dim_date",
        "fact_orders",
        "fact_order_items",
        "fact_payments",
        "fact_reviews",
    ]
    with engine.connect() as conn:
        for t in dim_fact_tables:
            res = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            dimensional_counts[t] = int(res) if res is not None else 0

    # Validate zero-value voucher preservation (must be exactly 9)
    with engine.connect() as conn:
        voucher_count = conn.execute(
            text("SELECT COUNT(*) FROM fact_payments WHERE payment_value = 0.00")
        ).scalar()
        if voucher_count != 9:
            discrepancies.append(
                f"Zero-value voucher retention violation: expected 9, got {voucher_count}"
            )

    # Validate SLA eligibility (must be exactly 96,470 eligible; 8 delivered excluded)
    with engine.connect() as conn:
        sla_eligible = conn.execute(
            text("SELECT COUNT(*) FROM fact_orders WHERE is_eligible_for_sla = TRUE")
        ).scalar()
        if sla_eligible != 96470:
            discrepancies.append(
                f"SLA eligible order count mismatch: expected 96,470, got {sla_eligible}"
            )

        missing_timestamp_delivered = conn.execute(
            text(
                "SELECT COUNT(*) FROM fact_orders "
                "WHERE is_delivered = TRUE AND order_delivered_customer_date IS NULL"
            )
        ).scalar()
        if missing_timestamp_delivered != 8:
            discrepancies.append(
                f"Delivered missing customer delivery date count mismatch: expected 8, got {missing_timestamp_delivered}"
            )

    success = len(discrepancies) == 0
    message = "Pipeline completed successfully with zero discrepancies." if success else (
        f"Pipeline completed with {len(discrepancies)} discrepancies:\n" + "\n".join(discrepancies)
    )

    return LoadResult(
        success=success,
        staging_counts=staging_counts,
        dimensional_counts=dimensional_counts,
        discrepancies=discrepancies,
        message=message,
    )
