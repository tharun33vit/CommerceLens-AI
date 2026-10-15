"""
Data Cleaning and Transformation Pipeline for CommerceLens AI.

Applies strictly justified, reproducible, and auditable transformations:
- Normalizes postal codes (CEP) to 5-digit zero-padded strings.
- Standardizes 2-letter state codes to uppercase.
- Computes verified operational flags without silently dropping records.
- Creates aggregated geolocation centroids per zip code prefix (solving 1:N fan-out).
- Persists derived datasets separately under data/processed/ (Parquet / CSV).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


def clean_orders(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean and enrich orders dataset.
    Preserves all records; flags operational milestones and delivery flags.
    """
    cleaned = df.copy()

    # String stripping
    if "order_status" in cleaned.columns:
        cleaned["order_status"] = cleaned["order_status"].astype(str).str.strip().str.lower()

    # Derived delivery flags (strictly based on timestamps)
    is_delivered = cleaned["order_status"] == "delivered"
    cleaned["is_delivered"] = is_delivered

    # Calculate actual delivery delay relative to estimated SLA
    if "order_delivered_customer_date" in cleaned.columns and "order_estimated_delivery_date" in cleaned.columns:
        both_dates = cleaned["order_delivered_customer_date"].notnull() & cleaned["order_estimated_delivery_date"].notnull()
        cleaned["is_late"] = False
        cleaned.loc[both_dates, "is_late"] = (
            cleaned.loc[both_dates, "order_delivered_customer_date"] > cleaned.loc[both_dates, "order_estimated_delivery_date"]
        )
        
        # Lead time in days
        if "order_purchase_timestamp" in cleaned.columns:
            has_purchase = both_dates & cleaned["order_purchase_timestamp"].notnull()
            cleaned["delivery_lead_time_days"] = np.nan
            cleaned.loc[has_purchase, "delivery_lead_time_days"] = (
                (cleaned.loc[has_purchase, "order_delivered_customer_date"] - cleaned.loc[has_purchase, "order_purchase_timestamp"])
                .dt.total_seconds() / 86400.0
            )

        # Flag chronological anomalies (delivered before purchase)
        cleaned["has_timestamp_anomaly"] = False
        if "order_purchase_timestamp" in cleaned.columns:
            anomaly_mask = both_dates & (
                cleaned.loc[both_dates, "order_delivered_customer_date"] < cleaned.loc[both_dates, "order_purchase_timestamp"]
            )
            cleaned.loc[anomaly_mask, "has_timestamp_anomaly"] = True

    metrics = {
        "total_records": len(cleaned),
        "delivered_orders": int(cleaned["is_delivered"].sum()) if "is_delivered" in cleaned.columns else 0,
        "late_orders": int(cleaned["is_late"].sum()) if "is_late" in cleaned.columns else 0,
    }
    return cleaned, metrics


def clean_customers(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean customers dataset.
    Ensures 5-digit zip code formatting and normalized state codes.
    """
    cleaned = df.copy()

    if "customer_zip_code_prefix" in cleaned.columns:
        cleaned["customer_zip_code_prefix"] = (
            cleaned["customer_zip_code_prefix"].astype(str).str.split(".").str[0].str.zfill(5)
        )

    if "customer_state" in cleaned.columns:
        cleaned["customer_state"] = cleaned["customer_state"].astype(str).str.strip().str.upper()

    if "customer_city" in cleaned.columns:
        cleaned["customer_city"] = cleaned["customer_city"].astype(str).str.strip().str.lower()

    metrics = {
        "total_customers": len(cleaned),
        "distinct_unique_customers": cleaned["customer_unique_id"].nunique() if "customer_unique_id" in cleaned.columns else 0,
    }
    return cleaned, metrics


def clean_sellers(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean sellers dataset.
    Normalizes postal code and state codes.
    """
    cleaned = df.copy()

    if "seller_zip_code_prefix" in cleaned.columns:
        cleaned["seller_zip_code_prefix"] = (
            cleaned["seller_zip_code_prefix"].astype(str).str.split(".").str[0].str.zfill(5)
        )

    if "seller_state" in cleaned.columns:
        cleaned["seller_state"] = cleaned["seller_state"].astype(str).str.strip().str.upper()

    if "seller_city" in cleaned.columns:
        cleaned["seller_city"] = cleaned["seller_city"].astype(str).str.strip().str.lower()

    metrics = {"total_sellers": len(cleaned)}
    return cleaned, metrics


def clean_order_items(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean order items and compute item-level gross values.
    """
    cleaned = df.copy()

    if "price" in cleaned.columns and "freight_value" in cleaned.columns:
        cleaned["total_item_value"] = cleaned["price"] + cleaned["freight_value"]
        cleaned["is_negative_price"] = cleaned["price"] < 0
        cleaned["is_negative_freight"] = cleaned["freight_value"] < 0

    metrics = {
        "total_items": len(cleaned),
        "total_gmv": float(cleaned["price"].sum()) if "price" in cleaned.columns else 0.0,
        "total_freight": float(cleaned["freight_value"].sum()) if "freight_value" in cleaned.columns else 0.0,
    }
    return cleaned, metrics


def clean_products(
    df: pd.DataFrame,
    translation_df: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean products catalog and join English category translations.
    """
    cleaned = df.copy()

    null_cat_count = int(cleaned["product_category_name"].isnull().sum()) if "product_category_name" in cleaned.columns else 0
    unmatched_count = 0
    distinct_unmatched: List[str] = []

    if translation_df is not None and "product_category_name" in cleaned.columns:
        trans_map = dict(
            zip(
                translation_df["product_category_name"].dropna().astype(str).str.strip(),
                translation_df["product_category_name_english"].dropna().astype(str).str.strip(),
            )
        )
        # Map English translation only where product_category_name is non-null
        cleaned["product_category_name_english"] = pd.Series(index=cleaned.index, dtype="object")
        has_cat_mask = cleaned["product_category_name"].notnull()
        cleaned.loc[has_cat_mask, "product_category_name_english"] = (
            cleaned.loc[has_cat_mask, "product_category_name"].astype(str).str.strip().map(trans_map)
        )

        # Count unmapped non-null categories
        unmapped_mask = has_cat_mask & cleaned["product_category_name_english"].isnull()
        unmatched_count = int(unmapped_mask.sum())
        distinct_unmatched = sorted(cleaned.loc[unmapped_mask, "product_category_name"].unique().tolist())

    metrics = {
        "total_products": len(cleaned),
        "categories_count": cleaned["product_category_name"].nunique() if "product_category_name" in cleaned.columns else 0,
        "products_with_null_category": null_cat_count,
        "products_with_untranslated_category": unmatched_count,
        "distinct_untranslated_categories": distinct_unmatched,
    }
    return cleaned, metrics


def clean_geolocation(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Deduplicate and aggregate geolocation records into median centroid per zip prefix.
    This resolves the multiple-coordinate-per-zip problem without data loss for distance modeling.
    """
    cleaned = df.copy()

    if "geolocation_zip_code_prefix" in cleaned.columns:
        cleaned["zip_code_prefix"] = (
            cleaned["geolocation_zip_code_prefix"].astype(str).str.split(".").str[0].str.zfill(5)
        )

    # Filter extreme coordinates outside Brazil bounds: Lat [-35, 6], Long [-75, -33]
    valid_mask = (
        (cleaned["geolocation_lat"] >= -35.0) & (cleaned["geolocation_lat"] <= 6.0) &
        (cleaned["geolocation_lng"] >= -75.0) & (cleaned["geolocation_lng"] <= -33.0)
    )
    valid_geo = cleaned[valid_mask]

    # Compute median centroid per zip prefix
    centroids = (
        valid_geo.groupby("zip_code_prefix")
        .agg(
            median_lat=("geolocation_lat", "median"),
            median_lng=("geolocation_lng", "median"),
            state=("geolocation_state", "first"),
            city=("geolocation_city", "first"),
            sample_points_count=("geolocation_lat", "count"),
        )
        .reset_index()
    )

    metrics = {
        "raw_geo_points": len(df),
        "valid_geo_points": int(valid_mask.sum()),
        "distinct_zip_centroids": len(centroids),
    }
    return centroids, metrics


def clean_all_datasets(
    tables: Dict[str, pd.DataFrame]
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
    """
    Orchestrate cleaning across all loaded raw tables.
    """
    cleaned_tables: Dict[str, pd.DataFrame] = {}
    cleaning_summary: Dict[str, Any] = {}

    if "orders" in tables:
        cleaned_tables["orders"], cleaning_summary["orders"] = clean_orders(tables["orders"])

    if "customers" in tables:
        cleaned_tables["customers"], cleaning_summary["customers"] = clean_customers(tables["customers"])

    if "sellers" in tables:
        cleaned_tables["sellers"], cleaning_summary["sellers"] = clean_sellers(tables["sellers"])

    if "order_items" in tables:
        cleaned_tables["order_items"], cleaning_summary["order_items"] = clean_order_items(tables["order_items"])

    if "order_payments" in tables:
        cleaned_tables["order_payments"] = tables["order_payments"].copy()
        cleaning_summary["order_payments"] = {"total_records": len(tables["order_payments"])}

    if "order_reviews" in tables:
        cleaned_tables["order_reviews"] = tables["order_reviews"].copy()
        cleaning_summary["order_reviews"] = {"total_records": len(tables["order_reviews"])}

    if "products" in tables:
        trans_df = tables.get("category_translation")
        cleaned_tables["products"], cleaning_summary["products"] = clean_products(tables["products"], trans_df)

    if "category_translation" in tables:
        cleaned_tables["category_translation"] = tables["category_translation"].copy()

    if "geolocation" in tables:
        cleaned_tables["geolocation_centroids"], cleaning_summary["geolocation"] = clean_geolocation(tables["geolocation"])

    return cleaned_tables, cleaning_summary


def save_processed_datasets(
    cleaned_tables: Dict[str, pd.DataFrame],
    output_dir: Path,
    export_csv: bool = True,
) -> Dict[str, Path]:
    """
    Save derived datasets to data/processed/.
    Ensures idempotency and does not touch data/raw/.
    """
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    saved_files: Dict[str, Path] = {}

    for table_name, df in cleaned_tables.items():
        # Save as CSV for transparency and Power BI / DB loading
        if export_csv:
            csv_file = out_path / f"cleaned_{table_name}.csv"
            df.to_csv(csv_file, index=False, encoding="utf-8")
            saved_files[f"{table_name}_csv"] = csv_file

        # Save as Parquet if supported by installed pyarrow/fastparquet
        try:
            parquet_file = out_path / f"cleaned_{table_name}.parquet"
            df.to_parquet(parquet_file, index=False)
            saved_files[f"{table_name}_parquet"] = parquet_file
        except (ImportError, Exception):
            pass

    return saved_files
