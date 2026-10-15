"""
Review Intelligence Database Persistence
=========================================
Manages idempotent DDL and transactional upserts for review intelligence
analytical tables in PostgreSQL (fact_review_analysis and fact_review_themes).
"""

import json
import logging
from typing import Any, Dict, List, Set, Tuple
from sqlalchemy import text
from sqlalchemy.engine import Engine

from commercelens.llm.schema import ReviewAnalysisRecord

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
-- 1. Parent analysis table: 1 row per unique compound key (review_id, order_id)
CREATE TABLE IF NOT EXISTS fact_review_analysis (
    review_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL,
    sentiment_label VARCHAR(20) NOT NULL,
    primary_theme VARCHAR(50) NOT NULL,
    delivery_related BOOLEAN NOT NULL DEFAULT FALSE,
    product_quality_related BOOLEAN NOT NULL DEFAULT FALSE,
    seller_service_related BOOLEAN NOT NULL DEFAULT FALSE,
    packaging_related BOOLEAN NOT NULL DEFAULT FALSE,
    payment_or_pricing_related BOOLEAN NOT NULL DEFAULT FALSE,
    returns_or_refunds_related BOOLEAN NOT NULL DEFAULT FALSE,
    brief_summary TEXT,
    evidence_quotes JSONB,
    language VARCHAR(10) DEFAULT 'pt',
    confidence_band VARCHAR(10) DEFAULT 'medium',
    model_name VARCHAR(50) NOT NULL,
    prompt_version VARCHAR(20) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    error_category VARCHAR(50),
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_fact_review_analysis PRIMARY KEY (review_id, order_id)
);

CREATE INDEX IF NOT EXISTS idx_fra_sentiment ON fact_review_analysis (sentiment_label);
CREATE INDEX IF NOT EXISTS idx_fra_primary_theme ON fact_review_analysis (primary_theme);
CREATE INDEX IF NOT EXISTS idx_fra_delivery_related ON fact_review_analysis (delivery_related);
CREATE INDEX IF NOT EXISTS idx_fra_order_id ON fact_review_analysis (order_id);

-- 2. Child normalized themes table: 1 row per (review_id, order_id, theme_id)
CREATE TABLE IF NOT EXISTS fact_review_themes (
    review_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL,
    theme_id VARCHAR(50) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT pk_fact_review_themes PRIMARY KEY (review_id, order_id, theme_id),
    CONSTRAINT fk_fact_review_themes_analysis 
        FOREIGN KEY (review_id, order_id) 
        REFERENCES fact_review_analysis (review_id, order_id) 
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_frt_theme_id ON fact_review_themes (theme_id);
"""


def create_review_analysis_tables(engine: Engine) -> None:
    """
    Creates fact_review_analysis and fact_review_themes idempotently.
    Never alters or drops existing tables or raw data.
    """
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLES_SQL))
    logger.info("Ensured review analysis tables exist in database.")


def get_processed_review_keys(engine: Engine) -> Set[Tuple[str, str]]:
    """
    Retrieves the set of already processed (review_id, order_id) compound keys
    to support seamless, idempotent resumption without duplicate work.
    """
    query = text("SELECT review_id, order_id FROM fact_review_analysis WHERE status = 'completed'")
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
        return {(row[0], row[1]) for row in rows}


def get_failed_review_keys(engine: Engine) -> Set[Tuple[str, str]]:
    """
    Retrieves the set of (review_id, order_id) compound keys currently
    marked with status = 'failed' in fact_review_analysis.
    """
    query = text("SELECT review_id, order_id FROM fact_review_analysis WHERE status = 'failed'")
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
        return {(row[0], row[1]) for row in rows}


def save_review_analysis_batch(
    engine: Engine,
    records: List[ReviewAnalysisRecord],
    protect_completed: bool = False,
) -> int:
    """
    Idempotently persists a batch of ReviewAnalysisRecord instances into
    fact_review_analysis and fact_review_themes inside a single database transaction.

    If protect_completed is True, any incoming records matching existing completed
    compound keys in fact_review_analysis are excluded to preserve immutable records.
    """
    if not records:
        return 0

    if protect_completed:
        completed_keys = get_processed_review_keys(engine)
        initial_len = len(records)
        records = [r for r in records if (r.review_id, r.order_id) not in completed_keys]
        skipped = initial_len - len(records)
        if skipped > 0:
            logger.info("protect_completed: skipped %d records that are already completed.", skipped)
        if not records:
            return 0

    upsert_parent_sql = text("""
        INSERT INTO fact_review_analysis (
            review_id, order_id, sentiment_label, primary_theme,
            delivery_related, product_quality_related, seller_service_related,
            packaging_related, payment_or_pricing_related, returns_or_refunds_related,
            brief_summary, evidence_quotes, language, confidence_band,
            model_name, prompt_version, content_hash, status, error_category, processed_at
        ) VALUES (
            :review_id, :order_id, :sentiment_label, :primary_theme,
            :delivery_related, :product_quality_related, :seller_service_related,
            :packaging_related, :payment_or_pricing_related, :returns_or_refunds_related,
            :brief_summary, CAST(:evidence_quotes AS jsonb), :language, :confidence_band,
            :model_name, :prompt_version, :content_hash, :status, :error_category, :processed_at
        )
        ON CONFLICT (review_id, order_id) DO UPDATE SET
            sentiment_label = EXCLUDED.sentiment_label,
            primary_theme = EXCLUDED.primary_theme,
            delivery_related = EXCLUDED.delivery_related,
            product_quality_related = EXCLUDED.product_quality_related,
            seller_service_related = EXCLUDED.seller_service_related,
            packaging_related = EXCLUDED.packaging_related,
            payment_or_pricing_related = EXCLUDED.payment_or_pricing_related,
            returns_or_refunds_related = EXCLUDED.returns_or_refunds_related,
            brief_summary = EXCLUDED.brief_summary,
            evidence_quotes = EXCLUDED.evidence_quotes,
            language = EXCLUDED.language,
            confidence_band = EXCLUDED.confidence_band,
            model_name = EXCLUDED.model_name,
            prompt_version = EXCLUDED.prompt_version,
            content_hash = EXCLUDED.content_hash,
            status = EXCLUDED.status,
            error_category = EXCLUDED.error_category,
            processed_at = EXCLUDED.processed_at;
    """)

    delete_themes_sql = text("""
        DELETE FROM fact_review_themes
        WHERE (review_id, order_id) IN (
            SELECT unnest(:review_ids), unnest(:order_ids)
        );
    """)

    insert_theme_sql = text("""
        INSERT INTO fact_review_themes (review_id, order_id, theme_id, is_primary)
        VALUES (:review_id, :order_id, :theme_id, :is_primary)
        ON CONFLICT (review_id, order_id, theme_id) DO NOTHING;
    """)

    parent_params = [r.to_parent_dict() for r in records]

    # Collect themes
    theme_params: List[Dict[str, Any]] = []
    for r in records:
        primary = r.primary_theme
        # Ensure all themes in r.themes are recorded
        unique_themes = set(r.themes)
        if primary:
            unique_themes.add(primary)
        
        for t in unique_themes:
            theme_params.append({
                "review_id": r.review_id,
                "order_id": r.order_id,
                "theme_id": t,
                "is_primary": (t == primary),
            })

    with engine.begin() as conn:
        # 1. Upsert parents
        conn.execute(upsert_parent_sql, parent_params)

        # 2. Re-insert child themes
        review_ids = [r.review_id for r in records]
        order_ids = [r.order_id for r in records]
        conn.execute(delete_themes_sql, {"review_ids": review_ids, "order_ids": order_ids})

        if theme_params:
            conn.execute(insert_theme_sql, theme_params)

    return len(records)
