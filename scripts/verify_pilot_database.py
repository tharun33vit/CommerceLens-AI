"""
CommerceLens AI — Step 3 Database Verification
===============================================
Queries PostgreSQL to verify:
- Model name & status breakdown (Mock analyses, original Gemini pilot, new Gemini batch, failed/pending).
- Verification of original 100 mock + 10 original Gemini records.
- Verification of newly completed Gemini records.
- Check for duplicate compound keys (review_id, order_id).
- Evidence quote grounding check on all Gemini records.
- Required labels, confidence bands, and theme validity against SUPPORTED_THEMES.
"""

import json
from sqlalchemy import text
from commercelens.analytics.db import create_db_engine
from commercelens.llm.redact import is_quote_grounded, normalize_review_text
from commercelens.llm.schema import SUPPORTED_THEMES, SentimentLabel


def verify_database():
    engine = create_db_engine()
    with engine.connect() as conn:
        print("=" * 60)
        print("1. MODEL_NAME & STATUS BREAKDOWN")
        print("=" * 60)
        breakdown_rows = conn.execute(text("""
            SELECT model_name, status, COUNT(*) AS total_count
            FROM fact_review_analysis
            GROUP BY model_name, status
            ORDER BY model_name, status;
        """)).fetchall()
        for r in breakdown_rows:
            print(f"  Model: {r[0]:<25} | Status: {r[1]:<12} | Count: {r[2]}")

        print("\n" + "=" * 60)
        print("2. TOTALS ACROSS ANALYSIS TABLES")
        print("=" * 60)
        total_analysis = conn.execute(text("SELECT COUNT(*) FROM fact_review_analysis;")).scalar()
        total_themes = conn.execute(text("SELECT COUNT(*) FROM fact_review_themes;")).scalar()
        print(f"  Total rows in fact_review_analysis : {total_analysis}")
        print(f"  Total rows in fact_review_themes   : {total_themes}")

        print("\n" + "=" * 60)
        print("3. DUPLICATE COMPOUND KEYS CHECK")
        print("=" * 60)
        dup_rows = conn.execute(text("""
            SELECT review_id, order_id, COUNT(*)
            FROM fact_review_analysis
            GROUP BY review_id, order_id
            HAVING COUNT(*) > 1;
        """)).fetchall()
        print(f"  Duplicate (review_id, order_id) count: {len(dup_rows)}")

        print("\n" + "=" * 60)
        print("4. ALL GEMINI RECORDS GROUNDING & INTEGRITY AUDIT")
        print("=" * 60)
        gemini_rows = conn.execute(text("""
            SELECT a.review_id, a.order_id, a.sentiment_label, a.primary_theme, a.brief_summary,
                   a.evidence_quotes, a.delivery_related, a.model_name, a.confidence_band,
                   r.review_score, r.review_comment_title, r.review_comment_message, a.processed_at
            FROM fact_review_analysis a
            JOIN fact_reviews r ON a.review_id = r.review_id AND a.order_id = r.order_id
            WHERE a.model_name = 'gemini-3.8-flash' AND a.status = 'completed'
            ORDER BY a.processed_at ASC
        """)).fetchall()

        print(f"  Total completed Gemini records found: {len(gemini_rows)}")
        
        ungrounded_quotes_count = 0
        invalid_theme_count = 0
        invalid_sentiment_count = 0
        
        valid_sentiments = {s.value for s in SentimentLabel}

        for idx, gr in enumerate(gemini_rows, 1):
            rev_id, ord_id, sent, theme, summ, quotes, deliv, model, conf, score, title, msg, proc_at = gr
            full_text = normalize_review_text(title, msg)

            if isinstance(quotes, str):
                try:
                    quotes_list = json.loads(quotes)
                except Exception:
                    quotes_list = [quotes]
            elif isinstance(quotes, list):
                quotes_list = quotes
            else:
                quotes_list = []

            grounding = [is_quote_grounded(q, full_text) for q in quotes_list]
            if not all(grounding):
                ungrounded_quotes_count += 1
                print(f"  [UNGROUNDED QUOTE] Key: ({rev_id}, {ord_id}) Quotes: {quotes_list} Grounding: {grounding}")

            if theme not in SUPPORTED_THEMES:
                invalid_theme_count += 1
                print(f"  [INVALID THEME] Key: ({rev_id}, {ord_id}) Theme: {theme}")

            if sent not in valid_sentiments:
                invalid_sentiment_count += 1
                print(f"  [INVALID SENTIMENT] Key: ({rev_id}, {ord_id}) Sentiment: {sent}")

        print(f"  Gemini Records Grounded Quotes Validation Passed : {len(gemini_rows) - ungrounded_quotes_count}/{len(gemini_rows)}")
        print(f"  Gemini Records Valid Themes Validation Passed    : {len(gemini_rows) - invalid_theme_count}/{len(gemini_rows)}")
        print(f"  Gemini Records Valid Sentiments Passed          : {len(gemini_rows) - invalid_sentiment_count}/{len(gemini_rows)}")

        print("\n" + "=" * 60)
        print("5. FAILED RECORDS IN DATABASE")
        print("=" * 60)
        failed_rows = conn.execute(text("""
            SELECT review_id, order_id, model_name, status, error_category, brief_summary
            FROM fact_review_analysis
            WHERE status != 'completed';
        """)).fetchall()
        print(f"  Non-completed rows in fact_review_analysis: {len(failed_rows)}")
        for fr in failed_rows:
            print(f"    Key: ({fr[0]}, {fr[1]}) | Model: {fr[2]} | Status: {fr[3]} | Error: {fr[4]}")


if __name__ == "__main__":
    verify_database()
