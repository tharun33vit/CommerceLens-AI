"""
Streamlit Data Access Layer & Caching
=====================================
Provides cached PostgreSQL query runners with grain discipline,
anti-fan-out protections, and safe fallback handling.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import streamlit as st

from commercelens.analytics.db import check_connection, create_db_engine


def get_engine():
    """Create a singleton SQLAlchemy engine for the Streamlit session."""
    return create_db_engine()


def check_db_health() -> Tuple[bool, str]:
    """Probes PostgreSQL database connectivity."""
    try:
        engine = get_engine()
        return check_connection(engine)
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=300, show_spinner=False)
def get_executive_kpis(
    selected_status: Optional[List[str]] = None,
    selected_state: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes verified executive metrics matching the Power BI reporting semantic layer.
    Uses Decimal for financial precision and safe NULL/zero handling.
    """
    engine = get_engine()
    state_filter = "AND dc.state = :state" if selected_state and selected_state != "All" else ""

    query = text(f"""
        SELECT
            COUNT(DISTINCT fo.order_id) AS total_orders,
            COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' THEN fo.order_id END) AS delivered_orders,
            COUNT(DISTINCT CASE WHEN fo.order_status = 'canceled' THEN fo.order_id END) AS canceled_orders,
            COUNT(DISTINCT CASE WHEN fo.order_status = 'unavailable' THEN fo.order_id END) AS unavailable_orders,
            COALESCE(SUM(CASE WHEN fo.order_status = 'delivered' THEN fo.total_item_merchandise_value ELSE 0 END), 0) AS total_gmv,
            COALESCE(SUM(CASE WHEN fo.order_status = 'delivered' THEN fo.total_freight_value ELSE 0 END), 0) AS total_freight,
            COUNT(DISTINCT CASE WHEN fo.is_eligible_for_sla THEN fo.order_id END) AS sla_eligible_orders,
            COUNT(DISTINCT CASE WHEN fo.is_eligible_for_sla AND fo.is_late = FALSE THEN fo.order_id END) AS on_time_orders,
            COUNT(DISTINCT CASE WHEN fo.is_eligible_for_sla AND fo.is_late = TRUE THEN fo.order_id END) AS late_orders,
            COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' AND fo.order_delivered_customer_date IS NULL THEN fo.order_id END) AS delivered_missing_timestamp
        FROM fact_orders fo
        JOIN dim_customers dc ON fo.customer_key = dc.customer_key
        WHERE 1=1 {state_filter};
    """)

    params = {}
    if selected_state and selected_state != "All":
        params["state"] = selected_state

    with engine.connect() as conn:
        row = conn.execute(query, params).mappings().fetchone()
        if not row:
            raise ValueError("No records found for executive KPIs query.")
        data = dict(row)

    total_orders = int(data.get("total_orders") or 0)
    delivered = int(data.get("delivered_orders") or 0)
    canceled = int(data.get("canceled_orders") or 0)
    unavailable = int(data.get("unavailable_orders") or 0)
    sla_eligible = int(data.get("sla_eligible_orders") or 0)
    on_time = int(data.get("on_time_orders") or 0)
    late = int(data.get("late_orders") or 0)

    # Use Decimal for financial precision
    raw_gmv = data.get("total_gmv")
    total_gmv = Decimal(str(raw_gmv)) if raw_gmv is not None else Decimal("0.00")

    raw_freight = data.get("total_freight")
    total_freight = Decimal(str(raw_freight)) if raw_freight is not None else Decimal("0.00")

    data["total_orders"] = total_orders
    data["delivered_orders"] = delivered
    data["canceled_orders"] = canceled
    data["unavailable_orders"] = unavailable
    data["sla_eligible_orders"] = sla_eligible
    data["on_time_orders"] = on_time
    data["late_orders"] = late
    data["total_gmv"] = total_gmv
    data["total_freight"] = total_freight

    # Financial AOV: Decimal calculation
    if delivered > 0:
        data["aov"] = (total_gmv / Decimal(str(delivered))).quantize(Decimal("0.01"))
    else:
        data["aov"] = Decimal("0.00")

    # Freight ratio percentage: Decimal calculation
    if total_gmv > Decimal("0"):
        data["freight_ratio_pct"] = ((total_freight / total_gmv) * Decimal("100")).quantize(Decimal("0.01"))
    else:
        data["freight_ratio_pct"] = Decimal("0.00")

    # Rates based on integer order counts
    data["on_time_rate_pct"] = round((on_time / sla_eligible) * 100.0, 2) if sla_eligible > 0 else 0.0
    data["late_rate_pct"] = round((late / sla_eligible) * 100.0, 2) if sla_eligible > 0 else 0.0
    data["canceled_rate_pct"] = round((canceled / total_orders) * 100.0, 2) if total_orders > 0 else 0.0
    data["unavailable_rate_pct"] = round((unavailable / total_orders) * 100.0, 2) if total_orders > 0 else 0.0

    return data


@st.cache_data(ttl=300, show_spinner=False)
def get_monthly_sales_trend() -> pd.DataFrame:
    """Retrieves monthly GMV and order volume from v_monthly_sales_performance."""
    engine = get_engine()
    query = text("""
        SELECT
            month_year,
            year,
            month,
            delivered_orders_count,
            delivered_item_merchandise_value AS gmv,
            delivered_freight_value AS freight,
            aov_delivered AS aov,
            mom_gmv_growth_pct
        FROM v_monthly_sales_performance
        ORDER BY year, month;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=300, show_spinner=False)
def get_category_performance(limit: int = 12) -> pd.DataFrame:
    """Retrieves top categories by GMV from v_category_merchandise_performance."""
    engine = get_engine()
    query = text("""
        SELECT
            revenue_rank,
            category_name,
            distinct_orders_count,
            items_sold_count,
            total_item_merchandise_value AS gmv,
            total_freight_value AS freight,
            cumulative_gmv_pct
        FROM v_category_merchandise_performance
        ORDER BY revenue_rank ASC
        LIMIT :limit;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


@st.cache_data(ttl=300, show_spinner=False)
def get_order_status_distribution() -> pd.DataFrame:
    """Retrieves distinct order count by order status."""
    engine = get_engine()
    query = text("""
        SELECT
            order_status,
            COUNT(DISTINCT order_id) AS order_count,
            ROUND((COUNT(DISTINCT order_id)::numeric / SUM(COUNT(DISTINCT order_id)) OVER ()) * 100, 2) AS percentage
        FROM fact_orders
        GROUP BY order_status
        ORDER BY order_count DESC;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=300, show_spinner=False)
def get_state_sales_distribution(limit: int = 15) -> pd.DataFrame:
    """Retrieves delivered GMV and order volume by customer state."""
    engine = get_engine()
    query = text("""
        SELECT
            dc.state AS customer_state,
            COUNT(DISTINCT fo.order_id) AS total_orders,
            COUNT(DISTINCT CASE WHEN fo.order_status = 'delivered' THEN fo.order_id END) AS delivered_orders,
            SUM(CASE WHEN fo.order_status = 'delivered' THEN fo.total_item_merchandise_value ELSE 0 END) AS delivered_gmv
        FROM fact_orders fo
        JOIN dim_customers dc ON fo.customer_key = dc.customer_key
        GROUP BY dc.state
        ORDER BY delivered_gmv DESC
        LIMIT :limit;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


@st.cache_data(ttl=300, show_spinner=False)
def get_review_intelligence_coverage() -> Dict[str, Any]:
    """Retrieves review processing coverage metrics from view_review_processing_coverage."""
    engine = get_engine()
    query = text("""
        SELECT * FROM view_review_processing_coverage;
    """)
    with engine.connect() as conn:
        row = conn.execute(query).mappings().fetchone()
        return dict(row) if row else {}


@st.cache_data(ttl=120, show_spinner=False)
def get_review_model_status_breakdown() -> Dict[str, Dict[str, int]]:
    """
    Retrieves counts of review analyses grouped by model_name and status from fact_review_analysis.
    Returns: {model_name: {'completed': count, 'failed': count, ...}, ...}
    """
    engine = get_engine()
    query = text("""
        SELECT model_name, status, COUNT(*) AS count
        FROM fact_review_analysis
        GROUP BY model_name, status
        ORDER BY model_name, status;
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
        breakdown: Dict[str, Dict[str, int]] = {}
        for model, status, count in rows:
            if model not in breakdown:
                breakdown[model] = {}
            breakdown[model][status] = int(count)
        return breakdown


def _resolve_engine_condition(engine_filter: Optional[str], col_prefix: str = "") -> Optional[str]:
    """
    Resolves SQL WHERE filter for the 4 distinct review intelligence cohorts:
    - 'All completed analyses' / 'All' -> None (all completed)
    - 'Gemini 3.5 Flash-Lite' -> model_name = 'gemini-3.5-flash-lite'
    - 'Gemini 3.8 Flash' -> model_name = 'gemini-3.8-flash'
    - 'Mock Portuguese NLP' -> model_name = 'mock-portuguese-nlp-v1'
    """
    if not engine_filter or engine_filter in ("All", "All completed analyses", "All Engines (Combined)"):
        return None
    col = f"{col_prefix}model_name" if col_prefix else "model_name"
    ef = engine_filter.strip().lower()
    if "3.5" in ef or "flash-lite" in ef:
        return f"{col} = 'gemini-3.5-flash-lite'"
    elif "3.8" in ef or ("flash" in ef and "lite" not in ef):
        return f"{col} = 'gemini-3.8-flash'"
    elif "mock" in ef:
        return f"{col} = 'mock-portuguese-nlp-v1'"
    elif "gemini" in ef:
        return f"{col} LIKE 'gemini%'"
    else:
        return f"{col} = :engine_filter"


@st.cache_data(ttl=120, show_spinner=False)
def get_review_sentiment_distribution(engine_filter: Optional[str] = None) -> pd.DataFrame:
    """Retrieves sentiment breakdown of completed reviews with strict cohort filtering."""
    engine = get_engine()
    conditions = ["status = 'completed'"]
    params: Dict[str, Any] = {}

    model_cond = _resolve_engine_condition(engine_filter)
    if model_cond:
        conditions.append(model_cond)
        if ":engine_filter" in model_cond:
            params["engine_filter"] = engine_filter

    where_clause = " AND ".join(conditions)
    query = text(f"""
        SELECT
            sentiment_label,
            COUNT(*) AS review_count,
            ROUND((COUNT(*)::numeric / NULLIF((SELECT COUNT(*) FROM fact_review_analysis WHERE {where_clause}), 0)) * 100, 2) AS percentage_share
        FROM fact_review_analysis
        WHERE {where_clause}
        GROUP BY sentiment_label
        ORDER BY review_count DESC;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


@st.cache_data(ttl=120, show_spinner=False)
def get_review_themes_breakdown(limit: int = 10, engine_filter: Optional[str] = None) -> pd.DataFrame:
    """Retrieves top review themes from completed reviews with strict cohort filtering."""
    engine = get_engine()
    conditions = ["a.status = 'completed'"]
    params: Dict[str, Any] = {"limit": limit}

    model_cond = _resolve_engine_condition(engine_filter, col_prefix="a.")
    if model_cond:
        conditions.append(model_cond)
        if ":engine_filter" in model_cond:
            params["engine_filter"] = engine_filter

    where_clause = " AND ".join(conditions)
    query = text(f"""
        SELECT
            t.theme_id,
            COUNT(*) AS occurrence_count,
            SUM(CASE WHEN t.is_primary THEN 1 ELSE 0 END) AS primary_theme_count
        FROM fact_review_themes t
        JOIN fact_review_analysis a ON t.review_id = a.review_id AND t.order_id = a.order_id
        WHERE {where_clause}
        GROUP BY t.theme_id
        ORDER BY occurrence_count DESC
        LIMIT :limit;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


@st.cache_data(ttl=300, show_spinner=False)
def get_review_delivery_cohort_breakdown() -> pd.DataFrame:
    """Retrieves delivery cohort sentiment cross-tabulation from view_review_delivery_cohort_analysis."""
    engine = get_engine()
    query = text("""
        SELECT * FROM view_review_delivery_cohort_analysis;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=120, show_spinner=False)
def get_review_model_breakdown() -> Dict[str, int]:
    """Retrieves counts of completed review analyses grouped by model_name."""
    engine = get_engine()
    query = text("""
        SELECT model_name, COUNT(*) AS count
        FROM fact_review_analysis
        WHERE status = 'completed'
        GROUP BY model_name;
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
        return {row[0]: int(row[1]) for row in rows}


@st.cache_data(ttl=120, show_spinner=False)
def get_filtered_review_explorer(
    sentiment: Optional[str] = None,
    theme: Optional[str] = None,
    score: Optional[int] = None,
    engine_filter: Optional[str] = None,
    limit: int = 50,
) -> pd.DataFrame:
    """
    Retrieves filtered processed reviews for UI exploration with PII protection.
    Excludes failed records (status='completed' strictly enforced).
    """
    engine = get_engine()
    conditions = ["a.status = 'completed'"]
    params: Dict[str, Any] = {"limit": limit}

    model_cond = _resolve_engine_condition(engine_filter, col_prefix="a.")
    if model_cond:
        conditions.append(model_cond)
        if ":engine_filter" in model_cond:
            params["engine_filter"] = engine_filter

    if sentiment and sentiment != "All":
        conditions.append("a.sentiment_label = :sentiment")
        params["sentiment"] = sentiment.lower()

    if theme and theme != "All":
        conditions.append("""
            EXISTS (
                SELECT 1 FROM fact_review_themes t 
                WHERE t.review_id = a.review_id AND t.order_id = a.order_id AND t.theme_id = :theme
            )
        """)
        params["theme"] = theme

    if score and score != 0:
        conditions.append("r.review_score = :score")
        params["score"] = score

    where_clause = " AND ".join(conditions)

    query = text(f"""
        SELECT
            a.review_id,
            a.order_id,
            r.review_score,
            a.sentiment_label,
            a.primary_theme,
            a.brief_summary,
            a.evidence_quotes::text AS evidence_quotes,
            a.delivery_related,
            a.confidence_band,
            a.model_name,
            a.status
        FROM fact_review_analysis a
        JOIN fact_reviews r ON a.review_id = r.review_id AND a.order_id = r.order_id
        WHERE {where_clause}
        ORDER BY a.processed_at DESC
        LIMIT :limit;
    """)

    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)
