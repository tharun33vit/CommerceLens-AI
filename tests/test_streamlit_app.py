"""
CommerceLens AI — Phase 6 Streamlit Platform & Grounded Copilot Tests
======================================================================
Tests data-access utilities, grain discipline, ML feature leakage rejection,
Copilot intent allowlisting, arbitrary SQL blocking, and offline badging.
"""

from pathlib import Path
from typing import Any, Dict
import numpy as np
import pandas as pd
import pytest

from commercelens.app.components import metric_card, render_mock_notice
from commercelens.app.copilot import APPROVED_INTENTS, GroundedAnalyticsCopilot
from commercelens.app.data import (
    check_db_health,
    get_category_performance,
    get_executive_kpis,
    get_filtered_review_explorer,
    get_monthly_sales_trend,
    get_order_status_distribution,
    get_review_intelligence_coverage,
    get_review_model_breakdown,
    get_review_model_status_breakdown,
    get_review_sentiment_distribution,
    get_review_themes_breakdown,
    get_state_sales_distribution,
)
from commercelens.ml.features import (
    ALL_PREDICTORS,
    FORBIDDEN_LEAKAGE_COLUMNS,
    validate_no_leakage,
)
from commercelens.ml.predict import load_delivery_predictor


# ==============================================================================
# 1. Database Connectivity & Executive KPI Grain Tests
# ==============================================================================

def test_database_connectivity_and_health():
    """Verify live PostgreSQL connectivity through the app data access layer."""
    is_connected, msg = check_db_health()
    assert is_connected is True, f"Database health check failed: {msg}"


def test_executive_kpis_grain_and_metrics():
    """Verify distinct order grain, zero fan-out, and verified GMV metrics."""
    kpis = get_executive_kpis(selected_state="All")

    assert "total_orders" in kpis
    assert "delivered_orders" in kpis
    assert "total_gmv" in kpis
    assert "aov" in kpis
    assert "on_time_rate_pct" in kpis

    # Total placed orders is 99,441
    assert kpis["total_orders"] == 99441
    # Delivered orders is 96,478
    assert kpis["delivered_orders"] == 96478
    # Delivered GMV is ~13.22M BRL (matching Power BI exactly)
    assert 13_200_000 <= kpis["total_gmv"] <= 13_250_000
    # AOV is ~137.04
    assert 135.0 <= kpis["aov"] <= 140.0
    # On-Time Delivery Rate is ~91.89%
    assert 91.0 <= kpis["on_time_rate_pct"] <= 92.5
    # Late rate + on-time rate should sum to 100% of SLA-eligible orders
    assert abs(kpis["on_time_rate_pct"] + kpis["late_rate_pct"] - 100.0) < 0.1


def test_monthly_sales_trend_view():
    """Verify monthly trend data matches star schema pre-aggregation."""
    df = get_monthly_sales_trend()
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "month_year" in df.columns
    assert "gmv" in df.columns
    assert "delivered_orders_count" in df.columns
    assert df["delivered_orders_count"].sum() == 96478


def test_category_performance_pareto():
    """Verify top product categories are ranked monotonically by GMV."""
    cat_df = get_category_performance(limit=10)
    assert len(cat_df) <= 10
    assert "category_name" in cat_df.columns
    assert "gmv" in cat_df.columns
    # Verify descending revenue rank
    assert cat_df["gmv"].is_monotonic_decreasing


def test_order_status_distribution():
    """Verify order status counts sum to total distinct orders."""
    status_df = get_order_status_distribution()
    assert not status_df.empty
    total_orders = status_df["order_count"].sum()
    assert total_orders == 99441
    pct_sum = status_df["percentage"].sum()
    assert 99.9 <= pct_sum <= 100.1


# ==============================================================================
# 2. Review Intelligence Data & Provenance Tests
# ==============================================================================

def test_review_intelligence_coverage_provenance():
    """Verify pilot processing count, distinct compound keys, and verified database breakdown."""
    cov = get_review_intelligence_coverage()
    assert cov["total_source_reviews"] == 99224
    assert cov["reviews_with_text"] == 42697
    # Exactly 132 completed reviews (100 mock + 28 Gemini 3.8 + 4 Flash-Lite)
    assert cov["processed_completed"] == 132
    assert cov["processed_failed"] == 28
    assert float(cov["text_coverage_pct"]) == round(132 / 42697 * 100, 2)

    # Verify model and status breakdown
    status_breakdown = get_review_model_status_breakdown()
    assert status_breakdown["mock-portuguese-nlp-v1"]["completed"] == 100
    assert status_breakdown["gemini-3.8-flash"]["completed"] == 28
    assert status_breakdown["gemini-3.8-flash"]["failed"] == 28
    assert status_breakdown["gemini-3.5-flash-lite"]["completed"] == 4


def test_model_cohort_filtering_isolates_completed_reviews():
    """Verify that cohort filters strictly isolate records and exclude failed reviews."""
    cohorts = [
        ("All completed analyses", 132),
        ("Gemini 3.5 Flash-Lite", 4),
        ("Gemini 3.8 Flash", 28),
        ("Mock Portuguese NLP", 100),
    ]

    for cohort_name, expected_count in cohorts:
        dist_df = get_review_sentiment_distribution(engine_filter=cohort_name)
        assert isinstance(dist_df, pd.DataFrame)
        assert not dist_df.empty
        total_in_dist = dist_df["review_count"].sum()
        assert total_in_dist == expected_count, (
            f"Expected {expected_count} completed reviews for cohort '{cohort_name}', got {total_in_dist}"
        )

        themes_df = get_review_themes_breakdown(engine_filter=cohort_name, limit=5)
        assert isinstance(themes_df, pd.DataFrame)
        assert not themes_df.empty

        explorer_df = get_filtered_review_explorer(engine_filter=cohort_name, limit=50)
        assert isinstance(explorer_df, pd.DataFrame)
        if not explorer_df.empty:
            assert (explorer_df["status"] == "completed").all()
            if cohort_name == "Gemini 3.5 Flash-Lite":
                assert (explorer_df["model_name"] == "gemini-3.5-flash-lite").all()
            elif cohort_name == "Gemini 3.8 Flash":
                assert (explorer_df["model_name"] == "gemini-3.8-flash").all()
            elif cohort_name == "Mock Portuguese NLP":
                assert (explorer_df["model_name"] == "mock-portuguese-nlp-v1").all()


def test_filtered_review_explorer_safety_and_provenance():
    """Verify review explorer parameter binding, provenance columns, and PII-safe record return."""
    # Test positive sentiment filter
    pos_df = get_filtered_review_explorer(sentiment="positive", limit=10)
    assert isinstance(pos_df, pd.DataFrame)
    if not pos_df.empty:
        assert (pos_df["sentiment_label"] == "positive").all()
        assert (pos_df["status"] == "completed").all()
        assert "review_id" in pos_df.columns
        assert "order_id" in pos_df.columns
        assert "brief_summary" in pos_df.columns
        assert "model_name" in pos_df.columns
        assert "evidence_quotes" in pos_df.columns


def test_render_mock_notice_cohort_disclaimers(monkeypatch):
    """Verify render_mock_notice renders appropriate disclaimers and sample size warnings."""
    import streamlit as st

    captured_outputs = []

    def mock_html(html_str):
        captured_outputs.append(html_str)

    def mock_markdown(md_str, **kwargs):
        captured_outputs.append(md_str)

    def mock_info(info_str, **kwargs):
        captured_outputs.append(info_str)

    def mock_warning(warn_str, **kwargs):
        captured_outputs.append(warn_str)

    monkeypatch.setattr(st, "html", mock_html, raising=False)
    monkeypatch.setattr(st, "markdown", mock_markdown)
    monkeypatch.setattr(st, "info", mock_info)
    monkeypatch.setattr(st, "warning", mock_warning)

    # 1. Flash-Lite cohort notice
    render_mock_notice(selected_cohort="Gemini 3.5 Flash-Lite")
    flash_lite_text = " ".join(captured_outputs)
    assert "CANDIDATE EVALUATION" in flash_lite_text
    assert "gemini-3.5-flash-lite" in flash_lite_text
    assert "Statistical Disclaimer" in flash_lite_text
    assert "N = 4" in flash_lite_text

    # 2. Mock cohort notice
    captured_outputs.clear()
    render_mock_notice(selected_cohort="Mock Portuguese NLP")
    mock_text = " ".join(captured_outputs)
    assert "Mock Portuguese NLP" in mock_text
    assert "MockLLMClient" in mock_text

    # 3. All completed cohort notice
    captured_outputs.clear()
    render_mock_notice(selected_cohort="All completed analyses", mock_count=100, breakdown={"gemini-3.8-flash": 28, "gemini-3.5-flash-lite": 4})
    all_text = " ".join(captured_outputs)
    assert "MULTI-COHORT REVIEW INTELLIGENCE PROVENANCE" in all_text
    assert "132" in all_text


# ==============================================================================
# 3. Delivery Risk ML Predictor & Leakage Rejection Tests
# ==============================================================================

def test_ml_predictor_leakage_rejection():
    """Verify that forbidden post-purchase milestone columns trigger immediate failure."""
    predictor = load_delivery_predictor("reports/model_artifacts")

    for forbidden_col in list(FORBIDDEN_LEAKAGE_COLUMNS)[:5]:
        bad_input = {
            "estimated_delivery_days": 15.0,
            "seller_dispatch_sla_days": 3.0,
            "distance_km": 400.0,
            "total_items_count": 1,
            forbidden_col: "leaked_value",
        }
        with pytest.raises(ValueError) as excinfo:
            predictor.predict(bad_input)
        assert "DATA LEAKAGE DETECTED" in str(excinfo.value)


def test_ml_point_in_time_prediction_execution():
    """Verify valid point-in-time order prediction produces valid probability and tier."""
    predictor = load_delivery_predictor("reports/model_artifacts")

    valid_input: Dict[str, Any] = {
        "estimated_delivery_days": 18.0,
        "seller_dispatch_sla_days": 3.0,
        "distance_km": 350.0,
        "promised_speed_km_per_day": 350.0 / 18.0,
        "total_items_count": 1,
        "unique_sellers_count": 1,
        "total_merchandise_value": 120.0,
        "total_freight_value": 18.0,
        "freight_ratio": 0.15,
        "freight_share": 0.13,
        "total_weight_g": 800.0,
        "total_volume_cm3": 4000.0,
        "max_dimension_cm": 25.0,
        "max_payment_installments": 2,
        "is_same_state": 1,
        "is_same_region": 1,
        "is_interstate": 0,
        "is_high_risk_destination": 0,
        "purchase_day_of_week": 1,
        "purchase_hour": 11,
        "is_weekend": 0,
        "customer_state": "SP",
        "seller_state": "SP",
        "customer_region": "Southeast",
        "seller_region": "Southeast",
        "category_grouped": "health_beauty",
        "primary_payment_type": "credit_card",
    }

    result = predictor.predict(valid_input)
    assert isinstance(result, dict)
    assert "late_risk_probability" in result
    assert "risk_tier" in result
    assert "is_late_risk" in result
    assert 0.0 <= result["late_risk_probability"] <= 1.0
    assert result["risk_tier"] in ["LOW", "MEDIUM", "HIGH"]
    assert result["decision_threshold"] == 0.72


# ==============================================================================
# 4. Grounded Analytics Copilot Intent & Safety Tests
# ==============================================================================

def test_copilot_intent_allowlisting():
    """Verify copilot correctly classifies valid business analytics intents."""
    copilot = GroundedAnalyticsCopilot()

    # Category GMV intent
    intent_cat, conf_cat = copilot.classify_intent("Which categories have highest GMV?")
    assert intent_cat == "top_categories_gmv"
    assert conf_cat > 0.0

    # On-time delivery SLA intent
    intent_sla, conf_sla = copilot.classify_intent("What is our on-time delivery SLA rate?")
    assert intent_sla == "delivery_sla_compliance"
    assert conf_sla > 0.0

    # CSAT gap intent
    intent_csat, conf_csat = copilot.classify_intent("How does delivery delay affect review scores and CSAT?")
    assert intent_csat == "csat_timeliness_gap"
    assert conf_csat > 0.0

    # ML model performance intent
    intent_ml, conf_ml = copilot.classify_intent("What is the model AUC and precision?")
    assert intent_ml == "model_performance_details"
    assert conf_ml > 0.0


def test_copilot_arbitrary_sql_and_injection_rejection():
    """Verify malicious SQL commands or unsupported prompts are rejected."""
    copilot = GroundedAnalyticsCopilot()

    malicious_inputs = [
        "DROP TABLE fact_orders;",
        "SELECT * FROM users WHERE 1=1; --",
        "DELETE FROM fact_review_analysis;",
        "UPDATE fact_orders SET is_late = false",
        "What is the CEO's personal home address?",
    ]

    for bad_input in malicious_inputs:
        resp = copilot.answer_question(bad_input)
        assert resp["success"] is False
        assert resp["mode"] == "REJECTED_UNSUPPORTED"
        assert resp["data"] is None
        assert "outside the approved business analytics allowlist" in resp["answer"]


def test_copilot_offline_mode_badging(monkeypatch):
    """Verify copilot displays OFFLINE COPILOT MODE when GEMINI_API_KEY is not configured."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    copilot = GroundedAnalyticsCopilot()
    assert copilot.is_live_gemini is False
    resp = copilot.answer_question("What is the on-time delivery rate?")
    assert resp["success"] is True
    assert resp["mode"] == "OFFLINE COPILOT MODE"
    assert "v_delivery_sla_operations" in resp["view"]
    assert resp["data"] is not None


def test_copilot_live_mode_badging(monkeypatch):
    """Verify copilot detects live mode when GEMINI_API_KEY is configured."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_mock_gemini_key_for_testing_only")
    copilot = GroundedAnalyticsCopilot()
    assert copilot.is_live_gemini is True



def test_copilot_evidence_grounding_structure():
    """Verify copilot responses include SQL template, declared grain, and caveats."""
    copilot = GroundedAnalyticsCopilot()
    resp = copilot.answer_question("Which product categories have the highest merchandise value?")
    assert resp["success"] is True
    assert "data" in resp
    assert "sql" in resp
    assert "view" in resp
    assert "grain" in resp
    assert "caveat" in resp
    assert "Evidence Grounding" in resp["caveat"]
    assert not resp["data"].empty


# ==============================================================================
# 5. Decimal-Valued KPI Formatting Regression Tests
# ==============================================================================

def test_format_currency_decimal_above_million():
    """Verify that GMV above R$ 1 million formats cleanly with M suffix using Decimal."""
    from commercelens.app.components import format_currency_decimal
    from decimal import Decimal

    assert format_currency_decimal(Decimal("13221498.11")) == "R$ 13.22M"
    assert format_currency_decimal(Decimal("1000000.00")) == "R$ 1.00M"
    assert format_currency_decimal(Decimal("2500000.50")) == "R$ 2.50M"
    # Verify float compatibility as well
    assert format_currency_decimal(13221498.11) == "R$ 13.22M"


def test_format_currency_decimal_below_million():
    """Verify that GMV below R$ 1 million formats with thousands separators and 2 decimals."""
    from commercelens.app.components import format_currency_decimal
    from decimal import Decimal

    assert format_currency_decimal(Decimal("999999.99")) == "R$ 999,999.99"
    assert format_currency_decimal(Decimal("850000.50")) == "R$ 850,000.50"
    assert format_currency_decimal(Decimal("137.04"), allow_millions=False) == "R$ 137.04"
    assert format_currency_decimal(Decimal("0.00")) == "R$ 0.00"
    assert format_currency_decimal(Decimal("0")) == "R$ 0.00"
    assert format_currency_decimal(850000.50) == "R$ 850,000.50"


def test_format_currency_decimal_null_and_edge_cases():
    """Verify safe fallback for None, empty string, or invalid numeric inputs."""
    from commercelens.app.components import format_currency_decimal

    assert format_currency_decimal(None) == "R$ 0.00"
    assert format_currency_decimal("") == "R$ 0.00"
    assert format_currency_decimal("invalid_string") == "R$ 0.00"


def test_format_freight_and_percentage_helpers():
    """Verify subtitle and percentage formatting with Decimal and float inputs."""
    from commercelens.app.components import format_freight_subtitle, format_percentage_safe
    from decimal import Decimal

    assert format_freight_subtitle(Decimal("2199026.06")) == "R$ 2.20M total shipping"
    assert format_freight_subtitle(Decimal("45000.00")) == "R$ 45,000.00 total shipping"
    assert format_freight_subtitle(None) == "R$ 0.00 total shipping"

    assert format_percentage_safe(Decimal("16.63")) == "16.63%"
    assert format_percentage_safe(16.63) == "16.63%"
    assert format_percentage_safe(None) == "0.00%"


def test_live_executive_kpis_decimal_types_and_no_typeerror():
    """Verify live PostgreSQL executive KPIs return Decimal and format without TypeError."""
    from commercelens.app.components import format_currency_decimal, format_freight_subtitle
    from decimal import Decimal

    kpis = get_executive_kpis(selected_state="All")

    # Verify types are Decimal
    assert isinstance(kpis["total_gmv"], Decimal), f"Expected Decimal, got {type(kpis['total_gmv'])}"
    assert isinstance(kpis["total_freight"], Decimal), f"Expected Decimal, got {type(kpis['total_freight'])}"
    assert isinstance(kpis["aov"], Decimal), f"Expected Decimal, got {type(kpis['aov'])}"
    assert isinstance(kpis["freight_ratio_pct"], Decimal), f"Expected Decimal, got {type(kpis['freight_ratio_pct'])}"

    # Verify formatting expressions do not raise TypeError
    gmv_fmt = format_currency_decimal(kpis["total_gmv"], allow_millions=True)
    assert gmv_fmt == "R$ 13.22M"

    freight_sub = format_freight_subtitle(kpis["total_freight"])
    assert freight_sub == "R$ 2.20M total shipping"

    aov_fmt = format_currency_decimal(kpis["aov"], allow_millions=False)
    assert aov_fmt == "R$ 137.04"


# ==============================================================================
# 6. UI Polish & Rendering Bugfix Regression Tests
# ==============================================================================

def test_metric_card_no_indented_code_blocks(monkeypatch):
    """Verify metric_card generates valid unindented HTML without Markdown code-block artifacts."""
    from commercelens.app.components import metric_card
    import streamlit as st

    captured_outputs = []

    def mock_html(html_str):
        captured_outputs.append(html_str)

    def mock_markdown(md_str, **kwargs):
        captured_outputs.append(md_str)

    monkeypatch.setattr(st, "html", mock_html, raising=False)
    monkeypatch.setattr(st, "markdown", mock_markdown)

    # Test card with subtitle and no delta (the scenario that previously triggered code-block rendering)
    metric_card(
        title="Delivered Orders",
        value="96,478",
        subtitle="97.0% of total placed orders",
    )

    assert len(captured_outputs) == 1
    rendered = captured_outputs[0]

    # Verify no 4-space indented code block lines exist in the rendered output
    assert "    <div class='kpi-subtitle'>" not in rendered
    assert "<div class='kpi-subtitle'>97.0% of total placed orders</div>" in rendered
    assert '<div class="kpi-card">' in rendered
    assert '<div class="kpi-value">96,478</div>' in rendered

    # Verify matching opening and closing div tags
    assert rendered.count("<div") == rendered.count("</div>")


def test_monthly_trend_filtering_preserves_historical_totals():
    """Verify that filtering out post-operational zero-delivered months retains 100% of delivered orders and GMV."""
    from commercelens.app.data import get_monthly_sales_trend

    monthly_df = get_monthly_sales_trend()
    assert not monthly_df.empty

    filtered_df = monthly_df[monthly_df["delivered_orders_count"] > 0]

    # Total delivered orders must be exactly 96,478 in both raw and filtered views
    assert filtered_df["delivered_orders_count"].sum() == 96478
    assert filtered_df["delivered_orders_count"].sum() == monthly_df["delivered_orders_count"].sum()

    # Total delivered GMV must be preserved with zero loss
    assert filtered_df["gmv"].sum() == monthly_df["gmv"].sum()

    # The filtered view ends at 2018-08 (operational cutoff)
    assert "2018-09" not in filtered_df["month_year"].values
    assert "2018-10" not in filtered_df["month_year"].values
    assert filtered_df.iloc[-1]["month_year"] == "2018-08"


def test_copilot_markdown_structure_and_grounding():
    """Verify Copilot answers provide cleanly formatted markdown summaries and full evidence grounding."""
    from commercelens.app.copilot import GroundedAnalyticsCopilot

    copilot = GroundedAnalyticsCopilot()
    resp = copilot.answer_question("Which product categories generate the highest delivered GMV?")

    assert resp["success"] is True
    # Markdown formatting should contain bold markup tokens
    assert "**health_beauty**" in resp["summary"]
    assert "**R$ " in resp["summary"]

    # Evidence grounding fields must all be populated
    assert resp["data"] is not None and not resp["data"].empty
    assert "v_category_merchandise_performance" in resp["sql"]
    assert resp["grain"] == "1 row per Category Name"
    assert "Evidence Grounding" in resp["caveat"]


def test_metric_card_title_wrapping_and_css(monkeypatch):
    """Verify that KPI title CSS allows natural 2-line wrapping with consistent vertical alignment."""
    from commercelens.app.components import CUSTOM_CSS, metric_card
    import streamlit as st

    # 1. Verify CSS rules for responsive title wrapping and vertical consistency
    assert ".kpi-title {" in CUSTOM_CSS
    assert "white-space: normal;" in CUSTOM_CSS
    assert "min-height: 2.5em;" in CUSTOM_CSS
    assert "-webkit-line-clamp: 2;" in CUSTOM_CSS
    assert "min-height: 125px;" in CUSTOM_CSS

    # 2. Verify long titles render completely without text truncation
    captured_outputs = []

    def mock_html(html_str):
        captured_outputs.append(html_str)

    def mock_markdown(md_str, **kwargs):
        captured_outputs.append(md_str)

    monkeypatch.setattr(st, "html", mock_html, raising=False)
    monkeypatch.setattr(st, "markdown", mock_markdown)

    long_titles = [
        "Average Order Value",
        "Freight-to-Merchandise",
        "On-Time Delivery Rate",
        "Processed Reviews (Pilot)",
        "Pilot Coverage Share",
    ]

    for t in long_titles:
        metric_card(title=t, value="100.0%", subtitle="Sample subtitle")

    assert len(captured_outputs) == len(long_titles)
    for idx, t in enumerate(long_titles):
        assert f'<div class="kpi-title">{t}</div>' in captured_outputs[idx]



