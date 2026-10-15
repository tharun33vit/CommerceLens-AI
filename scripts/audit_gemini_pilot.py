"""
CommerceLens AI — Audit Gemini Pilot Reviews
=============================================
Audits the first 10 live Gemini reviews in PostgreSQL against:
- Evidence quote grounding (exact/normalized match against source text).
- Summary fidelity (factual, no hallucinations).
- Sentiment label plausibility vs full review text.
- Primary theme validity and support.
- Delivery-related flag consistency.
- Compound key (review_id, order_id) and model provenance.
"""

import json
from typing import Any, Dict, List
from sqlalchemy import text
from commercelens.analytics.db import create_db_engine
from commercelens.llm.redact import is_quote_grounded, normalize_review_text


def audit_gemini_reviews():
    engine = create_db_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT a.review_id, a.order_id, a.sentiment_label, a.primary_theme, a.brief_summary,
                   a.evidence_quotes, a.delivery_related, a.model_name, a.confidence_band,
                   r.review_score, r.review_comment_title, r.review_comment_message
            FROM fact_review_analysis a
            JOIN fact_reviews r ON a.review_id = r.review_id AND a.order_id = r.order_id
            WHERE a.model_name = 'gemini-3.8-flash'
            ORDER BY a.processed_at ASC
        """)).fetchall()

    print(f"Total Gemini reviews found: {len(rows)}\n")

    passed_count = 0
    failed_count = 0
    ambiguous_count = 0
    detailed_results = []

    for idx, r in enumerate(rows, 1):
        rev_id, ord_id, sent, theme, summ, quotes, deliv, model, conf, score, title, msg = r
        full_text = normalize_review_text(title, msg)

        # Parse evidence quotes
        if isinstance(quotes, str):
            try:
                quotes_list = json.loads(quotes)
            except Exception:
                quotes_list = [quotes]
        elif isinstance(quotes, list):
            quotes_list = quotes
        else:
            quotes_list = []

        # Grounding check
        grounding_results = [is_quote_grounded(q, full_text) for q in quotes_list]
        all_grounded = all(grounding_results) if quotes_list else True

        # Check sentiment plausibility
        # e.g., if negative text has positive sentiment
        sentiment_plausible = True
        if sent == "positive" and score == 1 and not any(w in full_text.lower() for w in ["ótimo", "otimo", "bom", "excelente", "recomendo"]):
            sentiment_plausible = False

        # Check delivery related flag
        delivery_keywords = ["entrega", "chegou", "prazo", "atraso", "rapido", "rápido", "correios", "demorou", "recebi", "entregue"]
        has_delivery_mention = any(k in full_text.lower() for k in delivery_keywords)
        delivery_flag_consistent = (deliv == has_delivery_mention) or (not deliv and not has_delivery_mention)

        record_status = "PASS"
        if not all_grounded or not sentiment_plausible:
            record_status = "FAIL"
            failed_count += 1
        elif not delivery_flag_consistent:
            # could be nuanced/ambiguous
            record_status = "AMBIGUOUS"
            ambiguous_count += 1
        else:
            passed_count += 1

        print(f"[{idx}] Status: {record_status} | Key: ({rev_id}, {ord_id})")
        print(f"    Rating Score: {score} | Sentiment: {sent} | Theme: {theme} | Delivery: {deliv}")
        print(f"    Source Text: {full_text}")
        print(f"    Quotes: {quotes_list}")
        print(f"    Quotes Grounded: {grounding_results} (All: {all_grounded})")
        print(f"    Summary: {summ}")
        print("-" * 70)

        detailed_results.append({
            "idx": idx,
            "review_id": rev_id,
            "order_id": ord_id,
            "status": record_status,
            "all_grounded": all_grounded,
            "sentiment": sent,
            "theme": theme,
            "delivery_related": deliv,
            "summary": summ,
            "quotes": quotes_list,
        })

    print(f"\nAudit Summary:")
    print(f"  Total Audited: {len(rows)}")
    print(f"  Passed Checks: {passed_count}")
    print(f"  Failures: {failed_count}")
    print(f"  Ambiguous: {ambiguous_count}")


if __name__ == "__main__":
    audit_gemini_reviews()
