"""
Data Schema and Metadata Definitions for Olist E-Commerce Dataset.

This module defines expected filenames, candidate primary keys, foreign key
relationships, datetime fields, and Pydantic validation models for the
ingestion and quality audit pipeline.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Expected Raw Dataset Files
# -----------------------------------------------------------------------------
EXPECTED_RAW_FILES: Dict[str, str] = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# -----------------------------------------------------------------------------
# Candidate Primary Keys and Table Grain Definitions
# -----------------------------------------------------------------------------
CANDIDATE_PRIMARY_KEYS: Dict[str, List[str]] = {
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["review_id"],  # Also check compound ["review_id", "order_id"]
    "customers": ["customer_id"],
    "sellers": ["seller_id"],
    "products": ["product_id"],
    "geolocation": ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"],
    "category_translation": ["product_category_name"],
}

# -----------------------------------------------------------------------------
# Foreign Key Relationships: (child_table, child_col) -> (parent_table, parent_col)
# -----------------------------------------------------------------------------
EXPECTED_RELATIONSHIPS: List[Dict[str, str]] = [
    {
        "child_table": "order_items",
        "child_col": "order_id",
        "parent_table": "orders",
        "parent_col": "order_id",
        "relationship_name": "order_items_to_orders",
    },
    {
        "child_table": "order_items",
        "child_col": "product_id",
        "parent_table": "products",
        "parent_col": "product_id",
        "relationship_name": "order_items_to_products",
    },
    {
        "child_table": "order_items",
        "child_col": "seller_id",
        "parent_table": "sellers",
        "parent_col": "seller_id",
        "relationship_name": "order_items_to_sellers",
    },
    {
        "child_table": "order_payments",
        "child_col": "order_id",
        "parent_table": "orders",
        "parent_col": "order_id",
        "relationship_name": "order_payments_to_orders",
    },
    {
        "child_table": "order_reviews",
        "child_col": "order_id",
        "parent_table": "orders",
        "parent_col": "order_id",
        "relationship_name": "order_reviews_to_orders",
    },
    {
        "child_table": "orders",
        "child_col": "customer_id",
        "parent_table": "customers",
        "parent_col": "customer_id",
        "relationship_name": "orders_to_customers",
    },
    {
        "child_table": "products",
        "child_col": "product_category_name",
        "parent_table": "category_translation",
        "parent_col": "product_category_name",
        "relationship_name": "products_to_category_translation",
    },
]

# -----------------------------------------------------------------------------
# Datetime Columns by Table
# -----------------------------------------------------------------------------
DATETIME_COLUMNS: Dict[str, List[str]] = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": [
        "shipping_limit_date",
    ],
    "order_reviews": [
        "review_creation_date",
        "review_answer_timestamp",
    ],
}


# -----------------------------------------------------------------------------
# Finding Classification & Reporting Models
# -----------------------------------------------------------------------------
class FindingSeverity(str, Enum):
    CONFIRMED_ISSUE = "CONFIRMED_ISSUE"
    CANDIDATE_INVESTIGATION = "CANDIDATE_INVESTIGATION"
    EXPECTED_CHARACTERISTIC = "EXPECTED_CHARACTERISTIC"


class TableInventoryItem(BaseModel):
    table_name: str
    file_name: str
    file_size_bytes: int
    row_count: int
    column_count: int
    columns: List[str]
    inferred_types: Dict[str, str]
    datetime_columns_parsed: List[str]


class MissingValueStat(BaseModel):
    table_name: str
    column_name: str
    missing_count: int
    missing_percentage: float
    total_rows: int


class DuplicateStat(BaseModel):
    table_name: str
    total_rows: int
    complete_duplicates_count: int
    distinct_complete_rows: int
    complete_duplicates_percentage: float


class KeyValidationStat(BaseModel):
    table_name: str
    candidate_key: List[str]
    total_rows: int
    distinct_key_count: int
    duplicate_key_groups: int  # Distinct candidate-key values appearing > 1 time
    excess_duplicate_rows: int  # total_rows - distinct_key_count
    duplicate_key_count: int  # Alias for duplicate_key_groups for backward compatibility
    null_key_count: int
    is_valid_pk: bool
    notes: Optional[str] = None


class RelationshipValidationStat(BaseModel):
    relationship_name: str
    child_table: str
    child_col: str
    parent_table: str
    parent_col: str
    child_total_records: int
    child_null_records: int
    child_distinct_keys: int
    unmatched_child_records: int
    unmatched_child_keys: int
    referential_integrity_percentage: float
    is_clean: bool


class QualityFinding(BaseModel):
    finding_id: str
    table_name: str
    column_name: Optional[str] = None
    severity: FindingSeverity
    title: str
    evidence: str
    recommended_action: str
    is_safe_to_clean: bool = False
