"""
Review Intelligence Processing Pipeline
========================================
Orchestrates text extraction, PII redaction, caching, LLM analysis,
quote verification, database persistence, and progress tracking with
strict API cost controls and safety limits.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Set, Tuple
import pandas as pd
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine

from commercelens.llm.cache import ReviewAnalysisCache, compute_content_hash
from commercelens.llm.client import (
    GeminiQuotaExhaustedError,
    LLMClientBase,
    get_llm_client,
)
from commercelens.llm.persistence import (
    create_review_analysis_tables,
    get_failed_review_keys,
    get_processed_review_keys,
    save_review_analysis_batch,
)
from commercelens.llm.prompts import PROMPT_VERSION
from commercelens.llm.redact import (
    normalize_review_text,
    redact_personal_info,
    validate_and_filter_quotes,
)
from commercelens.llm.schema import ReviewAnalysisOutput, ReviewAnalysisRecord

logger = logging.getLogger(__name__)

# Safe default limit for runs without explicit arguments
DEFAULT_SAFE_LIMIT = 100


class ReviewIntelligencePipeline:
    """
    End-to-end customer review intelligence pipeline with controlled API usage,
    idempotent caching, and verified quote grounding.
    """

    def __init__(
        self,
        engine: Optional[Engine] = None,
        client: Optional[LLMClientBase] = None,
        cache: Optional[ReviewAnalysisCache] = None,
        batch_size: int = 50,
    ):
        self.engine = engine
        self.client = client or get_llm_client()
        self.cache = cache or ReviewAnalysisCache()
        self.batch_size = batch_size

    def extract_eligible_reviews(
        self,
        limit: Optional[int] = DEFAULT_SAFE_LIMIT,
        all_records: bool = False,
        resume: bool = False,
        retry_failed_only: bool = False,
    ) -> pd.DataFrame:
        """
        Extracts review records with valid text from fact_reviews.
        Ensures strict limits unless all_records is explicitly requested.
        Supports resume mode (skipping completed) and retry_failed_only mode (retrying failed).
        """
        if not self.engine:
            raise ValueError("Database engine is required to extract reviews.")

        if all_records and limit is not None:
            effective_limit = None
        else:
            effective_limit = limit if limit is not None else DEFAULT_SAFE_LIMIT

        # Build query
        base_query = """
            SELECT 
                review_id,
                order_id,
                review_score,
                review_comment_title,
                review_comment_message,
                review_creation_date
            FROM fact_reviews
            WHERE (review_comment_title IS NOT NULL AND TRIM(review_comment_title) != '')
               OR (review_comment_message IS NOT NULL AND TRIM(review_comment_message) != '')
            ORDER BY review_creation_date ASC, review_id ASC
        """

        with self.engine.connect() as conn:
            df = pd.read_sql(text(base_query), conn)

        # 1. Handle retry_failed_only mode (targets strictly failed records)
        if retry_failed_only:
            failed_keys = get_failed_review_keys(self.engine)
            completed_keys = get_processed_review_keys(self.engine)
            # Only reviews that are currently marked failed, strictly excluding completed
            df = df[
                df.apply(lambda r: (r["review_id"], r["order_id"]) in failed_keys, axis=1) &
                ~df.apply(lambda r: (r["review_id"], r["order_id"]) in completed_keys, axis=1)
            ]
            logger.info(
                "Retry-failed mode: identified %d eligible failed reviews to retry. Completed reviews skipped (immutable): %d.",
                len(df),
                len(completed_keys),
            )

        # 2. Handle standard resume mode (skipping already completed records)
        elif resume:
            processed_keys = get_processed_review_keys(self.engine)
            if processed_keys:
                initial_count = len(df)
                df = df[
                    ~df.apply(lambda r: (r["review_id"], r["order_id"]) in processed_keys, axis=1)
                ]
                logger.info(
                    "Resume mode: skipped %d already processed completed reviews. Remaining: %d.",
                    initial_count - len(df),
                    len(df),
                )

        if effective_limit and len(df) > effective_limit:
            df = df.iloc[:effective_limit].copy()

        return df

    def process_review(
        self,
        review_id: str,
        order_id: str,
        title: Optional[str],
        message: Optional[str],
    ) -> ReviewAnalysisRecord:
        """
        Processes a single review: normalizes, redacts PII, checks cache,
        invokes LLM, validates evidence quotes, and returns persistence record.
        """
        # 1. Normalize & Redact
        raw_combined = normalize_review_text(title, message)
        sanitized_text = redact_personal_info(raw_combined)

        if not sanitized_text.strip():
            # Fallback for empty text
            return ReviewAnalysisRecord(
                review_id=review_id,
                order_id=order_id,
                sentiment_label="unclear",
                primary_theme="unclear",
                themes=["unclear"],
                brief_summary="Texto ausente ou vazio.",
                evidence_quotes=[],
                language="pt",
                confidence_band="low",
                model_name=self.client.model_name,
                prompt_version=PROMPT_VERSION,
                content_hash=compute_content_hash("", self.client.model_name, PROMPT_VERSION),
                status="unclear",
            )

        content_hash = compute_content_hash(
            sanitized_text, self.client.model_name, PROMPT_VERSION
        )

        # 2. Check Cache
        cached_data = self.cache.get(content_hash)
        if cached_data:
            analysis_output = ReviewAnalysisOutput.model_validate(cached_data)
        else:
            # 3. Invoke LLM Client
            try:
                analysis_output = self.client.analyze_review(sanitized_text)
                self.cache.set(content_hash, analysis_output.model_dump())
            except GeminiQuotaExhaustedError:
                # Re-raise so pipeline.run halts the batch promptly and protects remaining reviews
                raise
            except Exception as e:
                error_cat = getattr(e, "error_category", None)
                if not error_cat:
                    if isinstance(e, json.JSONDecodeError):
                        error_cat = "JSONDecodeError"
                    elif isinstance(e, ValidationError):
                        error_cat = "SchemaValidationError"
                    else:
                        error_cat = type(e).__name__

                logger.error("LLM failure for review %s: [%s] %s", review_id, error_cat, str(e))
                return ReviewAnalysisRecord(
                    review_id=review_id,
                    order_id=order_id,
                    sentiment_label="unclear",
                    primary_theme="unclear",
                    themes=["unclear"],
                    brief_summary=f"Falha no processamento do modelo ({error_cat}).",
                    evidence_quotes=[],
                    language="pt",
                    confidence_band="low",
                    model_name=self.client.model_name,
                    prompt_version=PROMPT_VERSION,
                    content_hash=content_hash,
                    status="failed",
                    error_category=error_cat[:50],
                )

        # 4. Verify Evidence Quotes against source
        valid_quotes, rejected = validate_and_filter_quotes(
            analysis_output.evidence_quotes, sanitized_text
        )
        analysis_output.evidence_quotes = valid_quotes

        return ReviewAnalysisRecord(
            review_id=review_id,
            order_id=order_id,
            model_name=self.client.model_name,
            prompt_version=PROMPT_VERSION,
            content_hash=content_hash,
            status="completed",
            **analysis_output.model_dump(),
        )

    def run(
        self,
        limit: Optional[int] = DEFAULT_SAFE_LIMIT,
        all_records: bool = False,
        resume: bool = False,
        retry_failed_only: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes the pipeline over eligible reviews.
        Supports resume mode (skipping completed) and retry_failed_only mode.
        """
        start_time = time.time()

        if self.engine:
            create_review_analysis_tables(self.engine)

        df = self.extract_eligible_reviews(
            limit=limit,
            all_records=all_records,
            resume=resume,
            retry_failed_only=retry_failed_only,
        )
        total_to_process = len(df)

        if dry_run:
            completed_keys = get_processed_review_keys(self.engine) if self.engine else set()
            failed_keys = get_failed_review_keys(self.engine) if self.engine else set()
            logger.info("DRY-RUN: Found %d eligible reviews to process. Exiting.", total_to_process)
            return {
                "dry_run": True,
                "eligible_reviews_count": total_to_process,
                "retry_failed_only": retry_failed_only,
                "completed_skipped_count": len(completed_keys),
                "failed_available_count": len(failed_keys),
                "model_name": self.client.model_name,
                "prompt_version": PROMPT_VERSION,
            }

        logger.info(
            "Starting review intelligence pipeline: %d reviews to process using %s.",
            total_to_process,
            self.client.model_name,
        )

        processed_records: List[ReviewAnalysisRecord] = []
        batch: List[ReviewAnalysisRecord] = []
        success_count = 0
        failed_count = 0
        quota_exhausted = False
        quota_error_message = None

        for idx, row in df.iterrows():
            try:
                record = self.process_review(
                    review_id=row["review_id"],
                    order_id=row["order_id"],
                    title=row["review_comment_title"],
                    message=row["review_comment_message"],
                )
            except GeminiQuotaExhaustedError as qe:
                quota_exhausted = True
                quota_error_message = str(qe)
                logger.error(
                    "Gemini quota exhausted while processing review %s (order %s): %s. "
                    "Halting batch processing immediately. Unattempted reviews will not be marked failed.",
                    row["review_id"],
                    row["order_id"],
                    qe,
                )
                # Compute content hash for the failed record
                raw_combined = normalize_review_text(
                    row["review_comment_title"], row["review_comment_message"]
                )
                sanitized_text = redact_personal_info(raw_combined)
                content_hash = compute_content_hash(
                    sanitized_text, self.client.model_name, PROMPT_VERSION
                )
                failed_record = ReviewAnalysisRecord(
                    review_id=row["review_id"],
                    order_id=row["order_id"],
                    sentiment_label="unclear",
                    primary_theme="unclear",
                    themes=["unclear"],
                    brief_summary="Falha por esgotamento de cota da API (429 RESOURCE_EXHAUSTED).",
                    evidence_quotes=[],
                    language="pt",
                    confidence_band="low",
                    model_name=self.client.model_name,
                    prompt_version=PROMPT_VERSION,
                    content_hash=content_hash,
                    status="failed",
                    error_category="QuotaExhaustedError",
                )
                failed_count += 1
                processed_records.append(failed_record)
                batch.append(failed_record)
                # Terminate loop immediately: unattempted records are NOT processed or marked failed
                break

            if record.status == "completed":
                success_count += 1
            else:
                failed_count += 1

            processed_records.append(record)
            batch.append(record)

            # Batch persistence (strictly protecting completed records)
            if len(batch) >= self.batch_size:
                if self.engine:
                    save_review_analysis_batch(self.engine, batch, protect_completed=True)
                batch = []

            # Progress log every 25 records or at end
            current_count = len(processed_records)
            if current_count % 25 == 0 or current_count == total_to_process:
                elapsed = time.time() - start_time
                logger.info(
                    "Progress: %d/%d (%.1f%%) | Success: %d | Failed: %d | Elapsed: %.1fs",
                    current_count,
                    total_to_process,
                    (current_count / total_to_process) * 100 if total_to_process else 100,
                    success_count,
                    failed_count,
                    elapsed,
                )

        # Flush final batch (strictly protecting completed records)
        if batch and self.engine:
            save_review_analysis_batch(self.engine, batch, protect_completed=True)

        elapsed_total = time.time() - start_time
        token_usage = self.client.get_token_usage()

        return {
            "total_processed": len(processed_records),
            "success_count": success_count,
            "failed_count": failed_count,
            "elapsed_seconds": round(elapsed_total, 2),
            "model_name": self.client.model_name,
            "token_usage": token_usage,
            "records": processed_records,
            "quota_exhausted": quota_exhausted,
            "quota_error_message": quota_error_message,
        }
