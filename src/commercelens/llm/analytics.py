"""
Review Intelligence Analytics & Reporting
==========================================
Computes coverage metrics, sentiment distributions, theme frequencies,
rating-proxy concordance analysis, delivery-cohort correlations,
human annotation templates, and Markdown report generation.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

CAUSALITY_DISCLAIMER = (
    "Analytical Disclaimer: Statistical correlation between delivery timeliness and review sentiment "
    "does not establish direct causation. Confounding variables such as merchant responsiveness, "
    "packaging fragility, and carrier handling quality also influence customer satisfaction."
)


def calculate_processing_coverage(engine: Engine) -> Dict[str, Any]:
    """
    Computes global source review population and current processing coverage.
    """
    query = text("""
        SELECT
            (SELECT COUNT(*) FROM fact_reviews) AS total_source_reviews,
            (SELECT COUNT(DISTINCT (review_id, order_id)) FROM fact_reviews) AS distinct_compound_keys,
            (SELECT COUNT(*) FROM fact_reviews 
             WHERE (review_comment_title IS NOT NULL AND TRIM(review_comment_title) != '')
                OR (review_comment_message IS NOT NULL AND TRIM(review_comment_message) != '')
            ) AS reviews_with_text,
            (SELECT COUNT(*) FROM fact_reviews 
             WHERE (review_comment_title IS NULL OR TRIM(review_comment_title) = '')
               AND (review_comment_message IS NULL OR TRIM(review_comment_message) = '')
            ) AS reviews_without_text,
            (SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'completed') AS processed_completed,
            (SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'failed') AS processed_failed,
            (SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'unclear') AS processed_unclear
    """)
    with engine.connect() as conn:
        row = conn.execute(query).mappings().fetchone()
        data = dict(row)

    total_with_text = data["reviews_with_text"]
    processed_total = data["processed_completed"] + data["processed_failed"] + data["processed_unclear"]
    data["total_processed"] = processed_total
    data["coverage_percentage_of_text_reviews"] = (
        round((processed_total / total_with_text) * 100, 2) if total_with_text else 0.0
    )
    data["coverage_percentage_of_all_reviews"] = (
        round((processed_total / data["total_source_reviews"]) * 100, 2)
        if data["total_source_reviews"]
        else 0.0
    )
    return data


def calculate_sentiment_distribution(engine: Engine) -> pd.DataFrame:
    """Computes sentiment label counts and percentage shares among processed reviews."""
    query = text("""
        SELECT
            sentiment_label,
            COUNT(*) AS review_count,
            ROUND((COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (), 0)) * 100, 2) AS percentage_share
        FROM fact_review_analysis
        WHERE status = 'completed'
        GROUP BY sentiment_label
        ORDER BY review_count DESC;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def calculate_theme_frequencies(engine: Engine) -> pd.DataFrame:
    """Computes multi-label theme frequencies from fact_review_themes."""
    query = text("""
        SELECT
            theme_id,
            COUNT(*) AS occurrence_count,
            SUM(CASE WHEN is_primary THEN 1 ELSE 0 END) AS primary_theme_count,
            ROUND((COUNT(*)::numeric / NULLIF((SELECT COUNT(*) FROM fact_review_analysis WHERE status = 'completed'), 0)) * 100, 2) AS prevalence_percentage
        FROM fact_review_themes
        GROUP BY theme_id
        ORDER BY occurrence_count DESC;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def calculate_rating_proxy_agreement(engine: Engine) -> Dict[str, Any]:
    """
    Compares text-derived sentiment against customer rating proxy.
    Rating Proxy:
      Scores 1-2 -> negative_proxy
      Score 3    -> neutral_proxy
      Scores 4-5 -> positive_proxy
    """
    query = text("""
        SELECT
            r.review_score,
            CASE 
                WHEN r.review_score IN (1, 2) THEN 'negative_proxy'
                WHEN r.review_score = 3 THEN 'neutral_proxy'
                WHEN r.review_score IN (4, 5) THEN 'positive_proxy'
            END AS rating_proxy,
            a.sentiment_label,
            COUNT(*) AS count
        FROM fact_review_analysis a
        JOIN fact_reviews r ON a.review_id = r.review_id AND a.order_id = r.order_id
        WHERE a.status = 'completed'
        GROUP BY r.review_score, rating_proxy, a.sentiment_label
        ORDER BY r.review_score, count DESC;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if df.empty:
        return {"total_compared": 0, "matrix": [], "concordance_rate": 0.0}

    # Cross tab matrix
    pivot = df.pivot_table(
        index="rating_proxy",
        columns="sentiment_label",
        values="count",
        aggfunc="sum",
        fill_value=0,
    )

    total = df["count"].sum()
    # Direct matches: (negative_proxy & negative), (neutral_proxy & neutral), (positive_proxy & positive)
    direct_matches = 0
    if "negative_proxy" in pivot.index and "negative" in pivot.columns:
        direct_matches += pivot.loc["negative_proxy", "negative"]
    if "neutral_proxy" in pivot.index and "neutral" in pivot.columns:
        direct_matches += pivot.loc["neutral_proxy", "neutral"]
    if "positive_proxy" in pivot.index and "positive" in pivot.columns:
        direct_matches += pivot.loc["positive_proxy", "positive"]

    concordance_rate = round((direct_matches / total) * 100, 2) if total else 0.0

    return {
        "total_compared": int(total),
        "concordance_rate_pct": float(concordance_rate),
        "pivot_table": pivot.to_dict(),
        "raw_df": df,
    }


def calculate_delivery_cohort_sentiment(engine: Engine) -> pd.DataFrame:
    """
    Compares delivery complaint rates between on-time and late delivery cohorts.
    Requires join between fact_review_analysis, fact_reviews, and fact_orders.
    """
    query = text("""
        WITH order_delivery_status AS (
            SELECT
                order_id,
                CASE 
                    WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 'Late Delivery'
                    ELSE 'On-Time Delivery'
                END AS delivery_cohort
            FROM fact_orders
            WHERE order_status = 'delivered'
              AND order_delivered_customer_date IS NOT NULL
        )
        SELECT
            ods.delivery_cohort,
            COUNT(DISTINCT a.review_id || a.order_id) AS total_reviews_analyzed,
            SUM(CASE WHEN a.delivery_related THEN 1 ELSE 0 END) AS delivery_related_reviews,
            ROUND(
                (SUM(CASE WHEN a.delivery_related THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
                2
            ) AS delivery_related_pct,
            SUM(CASE WHEN a.primary_theme = 'delivery_delay' THEN 1 ELSE 0 END) AS delivery_delay_primary_count,
            ROUND(
                (SUM(CASE WHEN a.primary_theme = 'delivery_delay' THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
                2
            ) AS delivery_delay_primary_pct,
            SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END) AS negative_sentiment_count,
            ROUND(
                (SUM(CASE WHEN a.sentiment_label = 'negative' THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(DISTINCT a.review_id || a.order_id), 0)) * 100, 
                2
            ) AS negative_sentiment_pct
        FROM fact_review_analysis a
        JOIN order_delivery_status ods ON a.order_id = ods.order_id
        WHERE a.status = 'completed'
        GROUP BY ods.delivery_cohort
        ORDER BY ods.delivery_cohort;
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def generate_human_annotation_template(
    engine: Engine,
    output_path: Path,
    sample_size: int = 50,
) -> pd.DataFrame:
    """
    Generates a stratified CSV audit template for human double-blind verification.
    Leaves human annotations blank for reviewer entry.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    query = text("""
        SELECT
            a.review_id,
            a.order_id,
            r.review_score,
            COALESCE(r.review_comment_title, '') AS review_comment_title,
            COALESCE(r.review_comment_message, '') AS review_comment_message,
            a.sentiment_label AS llm_sentiment,
            a.primary_theme AS llm_primary_theme,
            a.confidence_band AS llm_confidence,
            a.brief_summary AS llm_summary
        FROM fact_review_analysis a
        JOIN fact_reviews r ON a.review_id = r.review_id AND a.order_id = r.order_id
        WHERE a.status = 'completed'
        ORDER BY RANDOM()
        LIMIT :sample_size
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"sample_size": sample_size})

    # Add empty human audit columns
    df["human_sentiment"] = ""
    df["human_primary_theme"] = ""
    df["human_delivery_related"] = ""
    df["human_reviewer_id"] = ""
    df["human_notes"] = ""

    df.to_csv(output_path, index=False, encoding="utf-8")
    return df


def generate_comprehensive_report(
    engine: Engine,
    output_dir: Path,
) -> Path:
    """
    Generates CSV exports and a Markdown summary report for review intelligence.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    coverage = calculate_processing_coverage(engine)
    sentiment_df = calculate_sentiment_distribution(engine)
    themes_df = calculate_theme_frequencies(engine)
    agreement = calculate_rating_proxy_agreement(engine)
    delivery_df = calculate_delivery_cohort_sentiment(engine)

    # Save CSVs
    sentiment_df.to_csv(output_dir / "sentiment_distribution.csv", index=False)
    themes_df.to_csv(output_dir / "theme_frequency.csv", index=False)
    if "raw_df" in agreement and not agreement["raw_df"].empty:
        agreement["raw_df"].to_csv(output_dir / "rating_sentiment_agreement.csv", index=False)
    delivery_df.to_csv(output_dir / "delivery_cohort_sentiment.csv", index=False)

    with open(output_dir / "processing_coverage.json", "w", encoding="utf-8") as f:
        json.dump(coverage, f, indent=2)

    # Build Markdown Report
    md_lines = [
        "# CommerceLens AI — Customer Review Intelligence Report",
        "",
        "> **Phase 5 Intelligence Artifact**: Natural Language Processing & Customer Feedback Mining",
        "",
        "---",
        "",
        "## 1. Executive Summary & Processing Coverage",
        "",
        f"- **Total Source Reviews**: {coverage.get('total_source_reviews', 0):,}",
        f"- **Eligible Reviews with Text**: {coverage.get('reviews_with_text', 0):,} ({round(coverage.get('reviews_with_text', 0) / max(coverage.get('total_source_reviews', 1), 1) * 100, 1)}% of total)",
        f"- **Reviews without Text**: {coverage.get('reviews_without_text', 0):,}",
        f"- **Processed Pilot Cohort**: {coverage.get('total_processed', 0):,} ({coverage.get('coverage_percentage_of_text_reviews', 0.0):.2f}% of text reviews)",
        f"- **Successfully Completed**: {coverage.get('processed_completed', 0):,}",
        f"- **Failed / Errors**: {coverage.get('processed_failed', 0):,}",
        "",
        "---",
        "",
        "## 2. Sentiment Distribution (Processed Cohort)",
        "",
    ]

    if not sentiment_df.empty:
        md_lines.append("| Sentiment Label | Review Count | Share (%) |")
        md_lines.append("|:---|:---:|:---:|")
        for _, r in sentiment_df.iterrows():
            md_lines.append(f"| **{r['sentiment_label']}** | {int(r['review_count']):,} | {r['percentage_share']:.2f}% |")
    else:
        md_lines.append("*No completed review analyses available.*")

    md_lines.extend([
        "",
        "---",
        "",
        "## 3. Review Theme Frequency & Prevalences",
        "",
    ])

    if not themes_df.empty:
        md_lines.append("| Theme Identifier | Total Occurrences | Primary Theme Count | Prevalence (%) |")
        md_lines.append("|:---|:---:|:---:|:---:|")
        for _, r in themes_df.iterrows():
            md_lines.append(f"| `{r['theme_id']}` | {int(r['occurrence_count']):,} | {int(r['primary_theme_count']):,} | {r['prevalence_percentage']:.2f}% |")
    else:
        md_lines.append("*No themes recorded.*")

    md_lines.extend([
        "",
        "---",
        "",
        "## 4. Rating Proxy vs Text Sentiment Concordance",
        "",
        f"- **Total Reviews Compared**: {agreement.get('total_compared', 0):,}",
        f"- **Concordance Rate**: **{agreement.get('concordance_rate_pct', 0.0):.2f}%**",
        "",
        "> [!NOTE]",
        "> **Analytical Caveat**: The rating proxy (Scores 1–2 = negative, Score 3 = neutral, Scores 4–5 = positive) is an operational comparison baseline, not a perfect ground-truth annotation. Customers frequently award high scores while noting minor complaints, or award low scores while expressing neutral or mixed text.",
        "",
        "---",
        "",
        "## 5. Delivery Timeliness Cohort vs Review Sentiment",
        "",
    ])

    if not delivery_df.empty:
        md_lines.append("| Delivery Cohort | Reviews Analyzed | Delivery-Related Reviews | Delivery Related (%) | Negative Sentiment (%) |")
        md_lines.append("|:---|:---:|:---:|:---:|:---:|")
        for _, r in delivery_df.iterrows():
            md_lines.append(f"| **{r['delivery_cohort']}** | {int(r['total_reviews_analyzed']):,} | {int(r['delivery_related_reviews']):,} | {r['delivery_related_pct']:.2f}% | {r['negative_sentiment_pct']:.2f}% |")
    else:
        md_lines.append("*No delivery cohort cross-tabulation available.*")

    md_lines.extend([
        "",
        "---",
        "",
        "## 6. Analytical Guardrails & Non-Causality",
        "",
        f"> {CAUSALITY_DISCLAIMER}",
        "",
    ])

    report_path = output_dir / "review_intelligence_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return report_path
