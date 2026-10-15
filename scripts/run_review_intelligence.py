#!/usr/bin/env python
"""
CommerceLens AI — Review Intelligence Pipeline Entry Point
===========================================================
Executes the customer review intelligence pipeline with controlled API limits,
structured outputs, caching, PostgreSQL persistence, and analytical reporting.

Usage:
    # Dry run preview (safe inspection)
    python scripts/run_review_intelligence.py --dry-run

    # Safe pilot run (default 100 reviews using active client / mock fallback)
    python scripts/run_review_intelligence.py --limit 100

    # Custom pilot limit
    python scripts/run_review_intelligence.py --limit 50 --resume

    # Force mock client execution (offline testing)
    python scripts/run_review_intelligence.py --mock --limit 100

    # Explicit full-dataset run (requires --all flag)
    python scripts/run_review_intelligence.py --all
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is in path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

load_dotenv()

from commercelens.analytics.db import create_db_engine
from commercelens.llm.analytics import (
    generate_comprehensive_report,
    generate_human_annotation_template,
)
from commercelens.llm.client import get_llm_client
from commercelens.llm.persistence import create_review_analysis_tables
from commercelens.llm.pipeline import ReviewIntelligencePipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("run_review_intelligence")


def main():
    parser = argparse.ArgumentParser(
        description="Run CommerceLens AI Review Intelligence Pipeline with LLM."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of eligible reviews to process (e.g. --limit 5; defaults to 10 for --retry-failed, 100 for standard/resume).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="process_all",
        help="Process ALL eligible reviews (42,697). Must be explicitly declared.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect eligible reviews without executing LLM calls or persisting data.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume processing, skipping already completed review compound keys.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Specifically target and retry records currently marked with status='failed' in fact_review_analysis.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force execution with deterministic Portuguese MockLLMClient.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model identifier (e.g. gemini-3.5-flash-lite, gemini-3.8-flash). Overrides GEMINI_MODEL env var.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/review_intelligence"),
        help="Directory to save analytical reports and CSV exports.",
    )

    args = parser.parse_args()

    # Safety constraint: enforce explicit confirmation for full dataset run
    if args.process_all:
        logger.warning(
            "====================================================================\n"
            "CRITICAL SAFETY WARNING: FULL DATASET PROCESSING REQUESTED (--all)\n"
            "This operation involves 42,697 customer reviews.\n"
            "If using live Gemini API, ensure quota and token budgets are approved.\n"
            "===================================================================="
        )
        effective_limit = None
    elif args.limit is not None:
        effective_limit = args.limit
        logger.info("Operating with explicit configured limit: %d reviews.", effective_limit)
    elif args.retry_failed:
        effective_limit = 10
        logger.info("Operating in SAFE RETRY-FAILED mode: default limit %d reviews.", effective_limit)
    else:
        effective_limit = 100
        logger.info("Operating in SAFE PILOT mode: default limit %d reviews.", effective_limit)

    engine = create_db_engine()
    create_review_analysis_tables(engine)

    # Initialize client with strict live validation (no silent mock fallback)
    if not args.mock:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            logger.error("Live processing requested, but GEMINI_API_KEY is not configured in .env.")
            print(
                "\n[ERROR] GEMINI_API_KEY is missing or empty in .env.\n"
                "To execute live Gemini processing, provide a valid GEMINI_API_KEY.\n"
                "To execute offline without API calls, pass the --mock flag explicitly.\n",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        client = get_llm_client(force_mock=args.mock, require_live=not args.mock, model_name=args.model)
    except Exception as e:
        logger.error("Failed to initialize LLM client: %s", e)
        print(f"\n[ERROR] Could not initialize LLM client: {e}\n", file=sys.stderr)
        sys.exit(1)

    logger.info("Resolved LLM provider: %s", client.model_name)

    pipeline = ReviewIntelligencePipeline(
        engine=engine,
        client=client,
    )

    result = pipeline.run(
        limit=effective_limit,
        all_records=args.process_all,
        resume=args.resume or args.retry_failed,
        retry_failed_only=args.retry_failed,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n--- DRY RUN SUMMARY ---")
        if args.retry_failed:
            print("Mode: RETRY-FAILED ONLY")
            print(f"Configured limit: {effective_limit if effective_limit is not None else 'ALL'}")
            print(f"Eligible failed reviews identified to retry: {result['eligible_reviews_count']}")
            print(f"Total available failed reviews in DB: {result.get('failed_available_count', 0)}")
            print(f"Completed reviews strictly skipped (immutable): {result.get('completed_skipped_count', 0)}")
        else:
            mode_str = "RESUME (skip completed)" if args.resume else "STANDARD"
            print(f"Mode: {mode_str}")
            print(f"Configured limit: {effective_limit if effective_limit is not None else 'ALL'}")
            print(f"Eligible reviews identified: {result['eligible_reviews_count']}")
            print(f"Completed reviews skipped (immutable): {result.get('completed_skipped_count', 0)}")
        print(f"Model configured: {result['model_name']}")
        print(f"Prompt version: {result['prompt_version']}")
        print("Dry run completed safely without API expenditure or database writes.\n")
        return

    # Deploy analytical SQL views
    views_sql_path = project_root / "sql" / "views" / "02_review_intelligence_views.sql"
    if views_sql_path.exists():
        from sqlalchemy import text
        with engine.begin() as conn:
            with open(views_sql_path, "r", encoding="utf-8") as f:
                conn.execute(text(f.read()))
        logger.info("Deployed review intelligence views from %s", views_sql_path.name)

    # Generate analytical reports and human audit template
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_file = generate_comprehensive_report(engine, args.output_dir)
    annotation_template = args.output_dir / "human_annotation_template.csv"
    generate_human_annotation_template(engine, annotation_template, sample_size=50)

    print("\n=======================================================")
    print("  COMMERCELENS AI — REVIEW INTELLIGENCE EXECUTION DONE")
    print("=======================================================")
    print(f"Processed records : {result['total_processed']}")
    print(f"Successful       : {result['success_count']}")
    print(f"Failed           : {result['failed_count']}")
    print(f"Elapsed Time     : {result['elapsed_seconds']}s")
    print(f"Model Used       : {result['model_name']}")
    print(f"Token Telemetry  : {result['token_usage']}")
    print(f"Markdown Report  : {report_file}")
    print(f"Human Template   : {annotation_template}")
    if result.get("quota_exhausted"):
        print("-------------------------------------------------------")
        print(" [WARNING] Gemini daily/project quota exhausted (429).")
        print(" Batch halted promptly to avoid wasted requests.")
        print(" Unattempted reviews remain intact and can be resumed later.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
