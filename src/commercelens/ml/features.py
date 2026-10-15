"""
CommerceLens AI — Machine Learning Feature Engineering & Leakage Prevention
=============================================================================
Builds an order-grain feature dataset using only predictors available at the
time of order placement. Implements strict data leakage rejection rules and
vectorized geographic calculations.
"""

from typing import Iterable, List, Set
import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

# ==============================================================================
# Strict Data Leakage Governance
# ==============================================================================
# Columns strictly forbidden as predictive inputs because they reflect post-purchase
# operational milestones, customer feedback, or target labels.
FORBIDDEN_LEAKAGE_COLUMNS: Set[str] = {
    "order_delivered_customer_date",
    "order_delivered_carrier_date",
    "delivery_lead_time_days",
    "carrier_transit_days",
    "seller_dispatch_days",
    "sla_variance_days",
    "is_late",
    "is_eligible_for_sla",
    "order_approved_at",
    "review_score",
    "review_comment_title",
    "review_comment_message",
    "review_creation_date",
    "review_answer_timestamp",
}

# Brazilian Federative Unit to Macro-Region Mapping
BRAZIL_MACRO_REGIONS = {
    # Southeast (Centro logístico principal)
    "SP": "Southeast", "RJ": "Southeast", "MG": "Southeast", "ES": "Southeast",
    # South (Sul)
    "PR": "South", "SC": "South", "RS": "South",
    # Northeast (Nordeste)
    "BA": "Northeast", "PE": "Northeast", "CE": "Northeast", "MA": "Northeast",
    "PB": "Northeast", "RN": "Northeast", "AL": "Northeast", "SE": "Northeast", "PI": "Northeast",
    # Central-West (Centro-Oeste)
    "DF": "Central-West", "GO": "Central-West", "MT": "Central-West", "MS": "Central-West",
    # North (Norte - Amazônia / long-haul river/air corridors)
    "PA": "North", "AM": "North", "RO": "North", "TO": "North",
    "AC": "North", "AP": "North", "RR": "North",
}

# Destinations with historically severe logistics and Correios fulfillment delay rates
HIGH_RISK_DESTINATIONS: Set[str] = {
    "RJ", "RR", "AP", "AM", "PA", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"
}

# Candidate Predictor Specification
NUMERIC_FEATURES: List[str] = [
    "estimated_delivery_days",
    "seller_dispatch_sla_days",
    "distance_km",
    "promised_speed_km_per_day",
    "total_items_count",
    "unique_sellers_count",
    "total_merchandise_value",
    "total_freight_value",
    "freight_ratio",
    "freight_share",
    "total_weight_g",
    "total_volume_cm3",
    "max_dimension_cm",
    "max_payment_installments",
    "is_same_state",
    "is_same_region",
    "is_interstate",
    "is_high_risk_destination",
    "purchase_day_of_week",
    "purchase_hour",
    "is_weekend",
]

CATEGORICAL_FEATURES: List[str] = [
    "customer_state",
    "seller_state",
    "customer_region",
    "seller_region",
    "category_grouped",
    "primary_payment_type",
]

ALL_PREDICTORS: List[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET_COLUMN: str = "is_late"


def validate_no_leakage(columns: Iterable[str]) -> None:
    """
    Assert that none of the forbidden data-leakage columns enter the feature set.
    
    Raises:
        ValueError: If any forbidden column name is detected.
    """
    cols_set = {str(c).lower().strip() for c in columns}
    leakage_present = cols_set.intersection({c.lower() for c in FORBIDDEN_LEAKAGE_COLUMNS})
    if leakage_present:
        raise ValueError(
            f"DATA LEAKAGE DETECTED! Forbidden features found in predictor matrix: {sorted(leakage_present)}. "
            f"These features represent post-order milestones or ground-truth outcomes."
        )


def haversine_distance(
    lat1: np.ndarray | pd.Series,
    lon1: np.ndarray | pd.Series,
    lat2: np.ndarray | pd.Series,
    lon2: np.ndarray | pd.Series,
) -> np.ndarray:
    """
    Compute geodesic distance (in kilometers) between two coordinates using Haversine formula.
    Handles missing coordinates safely by returning NaN.
    """
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    earth_radius_km = 6371.0088
    return earth_radius_km * c


def get_feature_extraction_sql() -> str:
    """
    Returns SQL query to extract the order-level feature dataset and label from PostgreSQL.
    Aggregates order items and payments to exactly one row per order_id before joining.
    Strictly filters out delivered orders missing customer delivery timestamps (the 8 exceptions).
    """
    return """
    WITH primary_item AS (
        SELECT DISTINCT ON (order_id)
            order_id,
            seller_key,
            product_key,
            shipping_limit_date
        FROM fact_order_items
        ORDER BY order_id, price DESC, order_item_id ASC
    ),
    item_agg AS (
        SELECT 
            foi.order_id,
            COUNT(foi.order_item_id)                                                        AS total_items_count,
            COUNT(DISTINCT foi.seller_key)                                                  AS unique_sellers_count,
            COUNT(DISTINCT foi.product_key)                                                 AS unique_products_count,
            COUNT(DISTINCT dp.category_name_english)                                        AS unique_categories_count,
            SUM(foi.price)                                                                  AS total_merchandise_value,
            SUM(foi.freight_value)                                                          AS total_freight_value,
            ROUND(AVG(foi.price), 2)                                                        AS avg_item_price,
            ROUND(AVG(foi.freight_value), 2)                                                AS avg_item_freight,
            MAX(foi.price)                                                                  AS max_item_price,
            MAX(foi.freight_value)                                                          AS max_item_freight,
            SUM(dp.product_weight_g)                                                        AS total_weight_g,
            MAX(dp.product_weight_g)                                                        AS max_weight_g,
            SUM(dp.product_length_cm * dp.product_height_cm * dp.product_width_cm)          AS total_volume_cm3,
            MAX(GREATEST(dp.product_length_cm, dp.product_height_cm, dp.product_width_cm))   AS max_dimension_cm
        FROM fact_order_items foi
        LEFT JOIN dim_products dp ON foi.product_key = dp.product_key
        GROUP BY foi.order_id
    ),
    payment_agg AS (
        SELECT 
            order_id,
            COUNT(DISTINCT payment_type)    AS payment_types_count,
            MAX(payment_installments)       AS max_payment_installments,
            COUNT(payment_sequential)       AS payment_sequential_count
        FROM fact_payments
        GROUP BY order_id
    ),
    primary_payment AS (
        SELECT DISTINCT ON (order_id)
            order_id,
            payment_type AS primary_payment_type
        FROM fact_payments
        ORDER BY order_id, payment_value DESC, payment_sequential ASC
    )
    SELECT 
        fo.order_id,
        fo.order_purchase_timestamp,
        fo.order_estimated_delivery_date,
        pi.shipping_limit_date,
        ROUND(EXTRACT(EPOCH FROM (fo.order_estimated_delivery_date - fo.order_purchase_timestamp)) / 86400.0, 2) AS estimated_delivery_days,
        ROUND(EXTRACT(EPOCH FROM (pi.shipping_limit_date - fo.order_purchase_timestamp)) / 86400.0, 2)           AS seller_dispatch_sla_days,
        -- Ground truth supervised label (1 = Late, 0 = On-time)
        CASE WHEN fo.order_delivered_customer_date > fo.order_estimated_delivery_date THEN 1 ELSE 0 END AS is_late,
        -- Customer Geography
        dc.state             AS customer_state,
        dc.zip_code_prefix   AS customer_zip_prefix,
        -- Primary Seller Geography
        ds.state             AS seller_state,
        ds.zip_code_prefix   AS seller_zip_prefix,
        CASE WHEN dc.state = ds.state THEN 1 ELSE 0 END AS is_same_state,
        -- Dominant Category
        COALESCE(dp_prim.category_name_english, 'unclassified') AS primary_category,
        -- Basket Aggregates
        ia.total_items_count,
        ia.unique_sellers_count,
        ia.unique_products_count,
        ia.unique_categories_count,
        ia.total_merchandise_value,
        ia.total_freight_value,
        ROUND(ia.total_freight_value / NULLIF(ia.total_merchandise_value, 0), 4) AS freight_ratio,
        ia.avg_item_price,
        ia.avg_item_freight,
        ia.max_item_price,
        ia.max_item_freight,
        ia.total_weight_g,
        ia.max_weight_g,
        ia.total_volume_cm3,
        ia.max_dimension_cm,
        -- Centroid Coordinates from dim_geography
        gc.latitude  AS customer_lat,
        gc.longitude AS customer_lng,
        gs.latitude  AS seller_lat,
        gs.longitude AS seller_lng,
        -- Payment Selection at checkout
        COALESCE(pp.primary_payment_type, 'unknown') AS primary_payment_type,
        COALESCE(pa.max_payment_installments, 1)     AS max_payment_installments
    FROM fact_orders fo
    JOIN dim_customers dc ON fo.customer_key = dc.customer_key
    JOIN primary_item pi ON fo.order_id = pi.order_id
    JOIN dim_sellers ds ON pi.seller_key = ds.seller_key
    LEFT JOIN dim_products dp_prim ON pi.product_key = dp_prim.product_key
    JOIN item_agg ia ON fo.order_id = ia.order_id
    LEFT JOIN payment_agg pa ON fo.order_id = pa.order_id
    LEFT JOIN primary_payment pp ON fo.order_id = pp.order_id
    LEFT JOIN dim_geography gc ON dc.zip_code_prefix = gc.zip_code_prefix
    LEFT JOIN dim_geography gs ON ds.zip_code_prefix = gs.zip_code_prefix
    WHERE fo.order_status = 'delivered'
      AND fo.order_delivered_customer_date IS NOT NULL
      AND fo.order_estimated_delivery_date IS NOT NULL
    ORDER BY fo.order_purchase_timestamp ASC;
    """


def extract_raw_features_from_db(engine: Engine) -> pd.DataFrame:
    """
    Executes the validated SQL query against PostgreSQL and returns the raw order dataframe.
    Validates that each order_id appears exactly once.
    """
    sql = get_feature_extraction_sql()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)

    if df["order_id"].duplicated().any():
        dups = df["order_id"].duplicated().sum()
        raise ValueError(f"Integrity check failed: found {dups} duplicate order_id records in feature extraction.")

    return df


def engineer_point_in_time_features(df: pd.DataFrame, top_categories: List[str] | None = None) -> pd.DataFrame:
    """
    Enriches the raw order data with derived point-in-time features.
    Guarantees no post-purchase milestone fields are used.
    
    Args:
        df: Raw feature dataframe from extract_raw_features_from_db or synthetic pipeline.
        top_categories: Optional list of top categories fitted from training data.
        
    Returns:
        pd.DataFrame with engineered point-in-time predictors.
    """
    out = df.copy()

    # Temporal feature extraction
    out["order_purchase_timestamp"] = pd.to_datetime(out["order_purchase_timestamp"])
    out["purchase_day_of_week"] = out["order_purchase_timestamp"].dt.dayofweek
    out["purchase_hour"] = out["order_purchase_timestamp"].dt.hour
    out["is_weekend"] = (out["purchase_day_of_week"] >= 5).astype(int)

    # Geographic Geodesic Distance
    out["distance_km"] = haversine_distance(
        out["customer_lat"], out["customer_lng"],
        out["seller_lat"], out["seller_lng"]
    )

    # Brazilian Macro-Regions
    out["customer_region"] = out["customer_state"].map(BRAZIL_MACRO_REGIONS).fillna("Other")
    out["seller_region"] = out["seller_state"].map(BRAZIL_MACRO_REGIONS).fillna("Other")
    out["is_same_region"] = (out["customer_region"] == out["seller_region"]).astype(int)
    out["is_interstate"] = (out["customer_state"] != out["seller_state"]).astype(int)

    # Promised Transit Speed (km per promised SLA day)
    out["promised_speed_km_per_day"] = out["distance_km"] / np.clip(out["estimated_delivery_days"], 1.0, None)

    # Freight cost intensity
    out["freight_share"] = out["total_freight_value"] / (
        out["total_merchandise_value"] + out["total_freight_value"] + 1e-4
    )

    # High-Risk Destination Indicator
    out["is_high_risk_destination"] = out["customer_state"].isin(HIGH_RISK_DESTINATIONS).astype(int)

    # Category Grouping (preserve dominant categories, collapse long tail)
    if top_categories is None:
        top_cats = out["primary_category"].value_counts().head(15).index.tolist()
    else:
        top_cats = top_categories

    out["category_grouped"] = out["primary_category"].apply(lambda c: c if c in top_cats else "other")

    return out
