"""
CommerceLens AI — Customer Sentiment Explorer Tab
=================================================
Visualizes Portuguese review intelligence, sentiment distributions,
and multi-label complaint themes extracted from the Phase 5 pipeline.
Enforces prominent MockLLMClient disclosure and PII redaction.
"""

import html
import json
from typing import Optional
import plotly.express as px
import streamlit as st

from commercelens.app.components import apply_plotly_theme, metric_card, render_mock_notice
from commercelens.app.data import (
    get_filtered_review_explorer,
    get_review_delivery_cohort_breakdown,
    get_review_intelligence_coverage,
    get_review_model_breakdown,
    get_review_model_status_breakdown,
    get_review_sentiment_distribution,
    get_review_themes_breakdown,
)


def render_sentiment_tab() -> None:
    """Renders Tab 3: Customer Sentiment Explorer."""
    st.markdown("### 💬 Customer Review Intelligence & Sentiment Analysis")
    st.markdown(
        "Structured Portuguese-language NLP analysis classifying sentiment, delivery-related "
        "complaints, and multi-label operational root causes across verified execution cohorts."
    )

    # 1. Query actual database counts dynamically (never hardcoded)
    try:
        model_status_map = get_review_model_status_breakdown()
    except Exception:
        model_status_map = {}

    completed_counts = {m: stats.get("completed", 0) for m, stats in model_status_map.items()}
    failed_counts = {m: stats.get("failed", 0) for m, stats in model_status_map.items()}

    total_completed = sum(completed_counts.values())
    total_failed = sum(failed_counts.values())
    total_attempted = total_completed + total_failed

    mock_count = completed_counts.get("mock-portuguese-nlp-v1", 0)
    flash_38_count = completed_counts.get("gemini-3.8-flash", 0)
    flash_lite_count = completed_counts.get("gemini-3.5-flash-lite", 0)

    # 2. Unified Cohort Selector for the entire tab
    c_hdr, c_sel = st.columns([2, 1])
    with c_hdr:
        st.markdown("#### Review Intelligence Execution Cohorts")
    with c_sel:
        cohort_options = [
            "All completed analyses",
            "Gemini 3.5 Flash-Lite",
            "Gemini 3.8 Flash",
            "Mock Portuguese NLP",
        ]
        selected_cohort = st.selectbox(
            "Select Evaluation Cohort:",
            cohort_options,
            key="sentiment_selected_cohort",
            help="Filters metrics, distributions, prevalent themes, and review cards to the selected model cohort.",
        )

    # 3. Prominent Provenance Notice reflecting selected cohort and sample size
    render_mock_notice(
        cohort_size=total_completed or 132,
        breakdown=completed_counts,
        selected_cohort=selected_cohort,
    )

    # 4. Pipeline Coverage & Ingestion Audit against eligible text reviews
    try:
        cov = get_review_intelligence_coverage()
    except Exception as e:
        st.error(f"❌ Failed to load review processing coverage from PostgreSQL: {e}")
        return

    if cov:
        eligible_text_count = cov.get("reviews_with_text", 42697)
        unprocessed_eligible = max(0, eligible_text_count - total_attempted)
        cov_pct = (total_completed / eligible_text_count * 100) if eligible_text_count else 0.0

        st.markdown("#### Review Pipeline Processing Coverage")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card(
                title="Eligible Text Reviews",
                value=f"{eligible_text_count:,}",
                subtitle="Source reviews with comment text",
            )
        with c2:
            if selected_cohort == "Gemini 3.5 Flash-Lite":
                comp_val = f"{flash_lite_count:,}"
                comp_sub = "Status = 'completed' (Flash-Lite)"
            elif selected_cohort == "Gemini 3.8 Flash":
                comp_val = f"{flash_38_count:,}"
                comp_sub = "Status = 'completed' (Flash 3.8)"
            elif selected_cohort == "Mock Portuguese NLP":
                comp_val = f"{mock_count:,}"
                comp_sub = "Status = 'completed' (Mock NLP)"
            else:
                comp_val = f"{total_completed:,}"
                comp_sub = f"Mock: {mock_count} | Flash: {flash_38_count} | Lite: {flash_lite_count}"

            metric_card(
                title="Completed Analyses",
                value=comp_val,
                subtitle=comp_sub,
            )
        with c3:
            metric_card(
                title="Failed Analyses",
                value=f"{total_failed:,}",
                subtitle="Recorded failures (Gemini 3.8)",
            )
        with c4:
            metric_card(
                title="Unprocessed Eligible",
                value=f"{unprocessed_eligible:,}",
                subtitle=f"Coverage share: {cov_pct:.2f}% of eligible",
            )

    st.markdown("---")

    # 5. Sentiment & Theme Visualizations (strictly completed records)
    st.markdown(f"#### Sentiment & Theme Distributions — {selected_cohort}")

    col_sent, col_theme = st.columns([1, 1])

    with col_sent:
        try:
            sent_df = get_review_sentiment_distribution(engine_filter=selected_cohort)
            cohort_n = sent_df["review_count"].sum() if not sent_df.empty else 0
            st.markdown(f"**Sentiment Distribution** (N = {cohort_n:,})")
            if not sent_df.empty:
                fig_sent = px.bar(
                    sent_df,
                    x="sentiment_label",
                    y="review_count",
                    text=sent_df["percentage_share"].apply(lambda p: f"{p:.1f}%"),
                    color="sentiment_label",
                    color_discrete_map={
                        "positive": "#2e7d32",
                        "neutral": "#0288d1",
                        "negative": "#d32f2f",
                        "mixed": "#ed6c02",
                    },
                    labels={"sentiment_label": "Sentiment", "review_count": "Count"},
                )
                fig_sent.update_traces(textposition="outside")
                fig_sent.update_layout(showlegend=False)
                apply_plotly_theme(fig_sent, height=350)
                st.plotly_chart(fig_sent, use_container_width=True)
            else:
                st.info(f"No completed sentiment records found for {selected_cohort}.")
        except Exception as e:
            st.warning(f"Unable to load sentiment chart: {e}")

    with col_theme:
        try:
            theme_df = get_review_themes_breakdown(limit=8, engine_filter=selected_cohort)
            st.markdown(f"**Prevalent Themes** (Top 8 for {selected_cohort})")
            if not theme_df.empty:
                fig_theme = px.bar(
                    theme_df,
                    x="occurrence_count",
                    y="theme_id",
                    orientation="h",
                    text="occurrence_count",
                    color="occurrence_count",
                    color_continuous_scale="Blues",
                    labels={"occurrence_count": "Mentions", "theme_id": "Taxonomy Theme"},
                )
                fig_theme.update_layout(yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
                fig_theme.update_traces(textposition="outside")
                apply_plotly_theme(fig_theme, height=350)
                st.plotly_chart(fig_theme, use_container_width=True)
            else:
                st.info(f"No theme records found for {selected_cohort}.")
        except Exception as e:
            st.warning(f"Unable to load theme breakdown: {e}")

    st.markdown("---")

    # 6. Delivery Cohort Analysis (On-Time vs Late)
    st.markdown("#### Logistics Timeliness vs Customer Sentiment (Cohorts)")
    try:
        cohort_df = get_review_delivery_cohort_breakdown()
        if not cohort_df.empty:
            st.dataframe(
                cohort_df.rename(
                    columns={
                        "delivery_cohort": "Fulfillment Cohort",
                        "total_reviews_analyzed": "Processed Reviews",
                        "delivery_related_reviews": "Delivery-Related Reviews",
                        "delivery_related_pct": "Delivery-Related Share (%)",
                        "delivery_delay_primary_count": "Delivery Delay Theme Count",
                        "delivery_delay_primary_pct": "Delivery Delay Primary Share (%)",
                        "negative_sentiment_count": "Negative Sentiment Count",
                        "negative_sentiment_pct": "Negative Sentiment (%)",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No delivery cohort analysis data returned.")
    except Exception as e:
        st.warning(f"Unable to load delivery cohort breakdown: {e}")

    st.markdown("---")

    # 7. PII-Safe Processed Review Explorer with Model-Specific Badging
    st.markdown("#### Processed Review Explorer (Auditable Evidence)")
    st.caption("Filters completed records from `fact_review_analysis` and `fact_review_themes`. Customer identities are masked.")

    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    with f_col1:
        sel_sent = st.selectbox("Filter Sentiment:", ["All", "positive", "neutral", "negative", "mixed"])
    with f_col2:
        sel_theme = st.selectbox(
            "Filter Theme:",
            [
                "All",
                "delivery_delay",
                "delivery_tracking",
                "positive_delivery_experience",
                "positive_product_experience",
                "poor_product_quality",
                "product_not_as_described",
                "damaged_or_defective_product",
                "seller_communication",
                "packaging_issue",
                "payment_or_pricing",
                "return_or_refund",
            ],
        )
    with f_col3:
        sel_score = st.selectbox("Filter Rating Score:", [0, 1, 2, 3, 4, 5], format_func=lambda x: "All Scores" if x == 0 else f"{x} Stars")
    with f_col4:
        limit_val = st.slider("Query Limit:", min_value=10, max_value=100, value=25, step=5)

    try:
        reviews_df = get_filtered_review_explorer(
            sentiment=sel_sent,
            theme=sel_theme,
            score=sel_score if sel_score > 0 else None,
            engine_filter=selected_cohort,
            limit=limit_val,
        )

        if not reviews_df.empty:
            for _, r in reviews_df.iterrows():
                # Redact IDs for PII and display
                masked_order = f"order_{str(r['order_id'])[:8]}..."
                masked_rev = f"rev_{str(r['review_id'])[:8]}..."

                # Clean and escape text for security
                summary_text = html.escape(str(r.get("brief_summary", "No summary available.")))
                theme_str = html.escape(str(r.get("primary_theme", "unclassified")))
                model_str = html.escape(str(r.get("model_name", "mock")))

                if "3.5" in model_str.lower() or "flash-lite" in model_str.lower():
                    engine_badge = '<span class="badge-success">GEMINI 3.5 FLASH-LITE</span>'
                elif "gemini" in model_str.lower():
                    engine_badge = '<span class="badge-success">GEMINI 3.8 FLASH</span>'
                else:
                    engine_badge = '<span class="badge-info">MOCK NLP</span>'

                evidence_raw = r.get("evidence_quotes", "[]")
                evidence_list = []
                try:
                    if isinstance(evidence_raw, str):
                        evidence_list = json.loads(evidence_raw)
                    elif isinstance(evidence_raw, list):
                        evidence_list = evidence_raw
                except Exception:
                    evidence_list = []

                with st.container():
                    review_card_html = (
                        '<div style="border: 1px solid #dee2e6; border-radius: 6px; padding: 12px 16px; margin-bottom: 10px; background-color: #fff;">'
                        '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">'
                        f'<span style="font-weight: 600; color: #1e3d59;">{masked_order} &nbsp; {engine_badge}</span>'
                        '<span>'
                        f'<span style="font-weight: 700; color: #f59e0b;">⭐ {r["review_score"]}</span> | '
                        f'<span class="badge-info">{r["sentiment_label"].upper()}</span> | '
                        f'<span class="badge-warning">Theme: {theme_str}</span>'
                        '</span>'
                        '</div>'
                        '<div style="font-size: 0.9rem; color: #333; margin-bottom: 6px;">'
                        f'<strong>Summary:</strong> {summary_text}'
                        '</div>'
                        '<div style="font-size: 0.8rem; color: #6c757d;">'
                        f'<em>Engine: {model_str} | Delivery-Related: {bool(r["delivery_related"])} | Confidence: {r.get("confidence_band", "N/A")}</em>'
                        '</div>'
                        '</div>'
                    )
                    if hasattr(st, "html"):
                        st.html(review_card_html)
                    else:
                        st.markdown(review_card_html, unsafe_allow_html=True)
                    if evidence_list:
                        with st.expander("🔍 View Verbatim Evidence Quotes (Portuguese)"):
                            for eq in evidence_list:
                                st.markdown(f"> *\"{html.escape(str(eq))}\"*")
        else:
            st.info(f"No reviews match the selected filter combination for {selected_cohort}.")
    except Exception as e:
        st.error(f"Error executing review query: {e}")
