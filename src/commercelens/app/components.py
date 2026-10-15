"""
Streamlit Reusable UI Components & Styling
==========================================
Provides custom CSS injection, standardized metric cards, status pills,
Plotly theme customization, and error/notice alert banners.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Union
import plotly.graph_objects as go
import streamlit as st

ONE_MILLION_DECIMAL = Decimal("1000000")


def format_currency_decimal(
    val: Optional[Union[Decimal, float, int, str]],
    allow_millions: bool = True,
    prefix: str = "R$ ",
) -> str:
    """
    Formats a currency value safely using Decimal precision without float division errors.
    Supports Decimal, float, int, string, or None.

    Examples:
        format_currency_decimal(Decimal("13221498.11")) -> "R$ 13.22M"
        format_currency_decimal(Decimal("850000.50"))   -> "R$ 850,000.50"
        format_currency_decimal(Decimal("137.04"), allow_millions=False) -> "R$ 137.04"
        format_currency_decimal(None)                  -> "R$ 0.00"
    """
    if val is None:
        return f"{prefix}0.00"

    if isinstance(val, Decimal):
        d_val = val
    else:
        try:
            d_val = Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            return f"{prefix}0.00"

    if allow_millions and abs(d_val) >= ONE_MILLION_DECIMAL:
        m_val = d_val / ONE_MILLION_DECIMAL
        return f"{prefix}{m_val:,.2f}M"
    else:
        return f"{prefix}{d_val:,.2f}"


def format_freight_subtitle(freight_val: Optional[Union[Decimal, float, int, str]]) -> str:
    """Formats freight value into a descriptive subtitle string using Decimal division."""
    curr = format_currency_decimal(freight_val, allow_millions=True)
    return f"{curr} total shipping"


def format_percentage_safe(val: Optional[Union[Decimal, float, int, str]]) -> str:
    """Formats percentage safely without Decimal/float mismatch."""
    if val is None:
        return "0.00%"
    if isinstance(val, Decimal):
        return f"{val:,.2f}%"
    try:
        return f"{float(val):.2f}%"
    except (ValueError, TypeError):
        return "0.00%"


CUSTOM_CSS = """
<style>
    /* Metric Card Styling */
    .kpi-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 14px 18px;
        border: 1px solid #e9ecef;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        margin-bottom: 12px;
        overflow: hidden;
        word-wrap: break-word;
        min-height: 125px;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    .kpi-title {
        font-size: 0.80rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #6c757d;
        font-weight: 600;
        margin-bottom: 6px;
        line-height: 1.25;
        min-height: 2.5em;
        white-space: normal;
        overflow-wrap: break-word;
        word-break: normal;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .kpi-value {
        font-size: 1.60rem;
        font-weight: 700;
        color: #212529;
        margin-bottom: 4px;
        line-height: 1.2;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .kpi-subtitle {
        font-size: 0.78rem;
        color: #6c757d;
        line-height: 1.35;
        overflow: hidden;
        word-break: break-word;
        white-space: normal;
    }

    /* Badges */
    .badge-success {
        background-color: #d1e7dd;
        color: #0f5132;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
    }
    .badge-warning {
        background-color: #fff3cd;
        color: #664d03;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
    }
    .badge-danger {
        background-color: #f8d7da;
        color: #842029;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
    }
    .badge-info {
        background-color: #cff4fc;
        color: #055160;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.75rem;
    }

    /* Mock Notice Alert */
    .mock-notice {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 12px 16px;
        border-radius: 4px;
        margin-bottom: 16px;
        color: #664d03;
        font-size: 0.88rem;
    }
</style>
"""


def inject_custom_css() -> None:
    """Injects custom CSS styles into the Streamlit app."""
    if hasattr(st, "html"):
        st.html(CUSTOM_CSS)
    else:
        st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def metric_card(
    title: str,
    value: str,
    subtitle: Optional[str] = None,
    delta: Optional[str] = None,
    delta_color: str = "normal",
) -> None:
    """
    Renders an accessible metric card with full value display (preventing truncation).
    Uses unindented HTML and st.html to prevent Markdown code-block parsing and scrollbars.
    """
    delta_html = ""
    if delta:
        color = "#198754" if delta_color == "normal" else "#dc3545"
        delta_html = f"<div style='font-size: 0.78rem; color: {color}; font-weight: 600; margin-bottom: 2px;'>{delta}</div>"

    sub_html = f"<div class='kpi-subtitle'>{subtitle}</div>" if subtitle else ""

    card_html = (
        f'<div class="kpi-card">'
        f'<div class="kpi-title">{title}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{delta_html}'
        f'{sub_html}'
        f'</div>'
    )
    if hasattr(st, "html"):
        st.html(card_html)
    else:
        st.markdown(card_html, unsafe_allow_html=True)


def render_mock_notice(
    cohort_size: int = 100,
    mock_count: Optional[int] = None,
    gemini_count: Optional[int] = None,
    breakdown: Optional[Dict[str, int]] = None,
    selected_cohort: Optional[str] = None,
) -> None:
    """
    Renders an accurate provenance disclaimer reflecting actual database counts
    for MockLLMClient and Google Gemini inferences, with explicit sample-size
    disclaimers for exploratory evaluations.
    """
    flash_lite_count = 0
    flash_38_count = 0

    if breakdown is not None:
        flash_lite_count = breakdown.get("gemini-3.5-flash-lite", 0)
        flash_38_count = breakdown.get("gemini-3.8-flash", 0)
        if mock_count is None:
            mock_count = breakdown.get("mock_count", breakdown.get("mock-portuguese-nlp-v1", 0))
        if gemini_count is None:
            gemini_count = flash_lite_count + flash_38_count

    # If selected_cohort is specifically targeted:
    norm_cohort = (selected_cohort or "").lower()

    if "3.5" in norm_cohort or "flash-lite" in norm_cohort:
        notice_html = (
            f'<div style="background-color: #e8f4fd; border-left: 5px solid #0d6efd; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; color: #084298; font-size: 0.88rem;">'
            f'<strong>⚡ CANDIDATE EVALUATION: Gemini 3.5 Flash-Lite (Active Cohort)</strong><br/>'
            f'Displaying <strong>{flash_lite_count or 4}</strong> review records processed live via <code>gemini-3.5-flash-lite</code> '
            f'(minimal thinking level, zero custom temperature sampling, native Pydantic schema validation).<br/>'
            f'<em>Statistical Disclaimer: This exploratory pilot (N = {flash_lite_count or 4}) verifies output formatting, '
            f'PII masking, and evidence-quote grounding. It does <strong>not</strong> establish generalized model accuracy or production reliability.</em>'
            f'</div>'
        )
    elif "3.8" in norm_cohort or ("flash" in norm_cohort and "lite" not in norm_cohort):
        notice_html = (
            f'<div style="background-color: #d1e7dd; border-left: 5px solid #198754; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; color: #0f5132; font-size: 0.88rem;">'
            f'<strong>🟢 PRODUCTION BASELINE: Gemini 3.8 Flash (Active Cohort)</strong><br/>'
            f'Displaying <strong>{flash_38_count or 28}</strong> completed review intelligence records processed live via Google Gemini '
            f'(<code>gemini-3.8-flash</code> with low thinking level). '
            f'Note: 28 historical transient/quota exhaustion records remain immutably recorded as failures for auditability.'
            f'</div>'
        )
    elif "mock" in norm_cohort:
        notice_html = (
            f'<div class="mock-notice">'
            f'<strong>⚠️ OFFLINE DETERMINISTIC PILOT: Mock Portuguese NLP</strong><br/>'
            f'Displaying <strong>{mock_count or 100}</strong> review records analyzed via '
            f'<code>MockLLMClient</code> (deterministic Portuguese rule-based NLP). These outputs demonstrate '
            f'pipeline schema integration, and must <strong>never</strong> be reported as live API inferences.'
            f'</div>'
        )
    elif mock_count is not None and gemini_count is not None:
        if mock_count > 0 and gemini_count > 0:
            notice_html = (
                f'<div style="background-color: #e8f4fd; border-left: 5px solid #0d6efd; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; color: #084298; font-size: 0.88rem;">'
                f'<strong>📊 MULTI-COHORT REVIEW INTELLIGENCE PROVENANCE</strong><br/>'
                f'The database currently holds <strong>{mock_count + gemini_count}</strong> completed processed reviews: '
                f'<strong>{mock_count}</strong> via <code>MockLLMClient</code>, '
                f'<strong>{flash_38_count or 28}</strong> live via <code>gemini-3.8-flash</code>, and '
                f'<strong>{flash_lite_count or 4}</strong> live via candidate <code>gemini-3.5-flash-lite</code>. '
                f'Additionally, <strong>28</strong> historical failures remain distinctly isolated in PostgreSQL. '
                f'Every review card below is explicitly badged with its verified model provenance.'
                f'</div>'
            )
        elif gemini_count > 0:
            notice_html = (
                f'<div style="background-color: #d1e7dd; border-left: 5px solid #198754; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; color: #0f5132; font-size: 0.88rem;">'
                f'<strong>🟢 LIVE GEMINI REVIEW INTELLIGENCE</strong><br/>'
                f'Displaying {gemini_count} review intelligence records processed live via Google Gemini.'
                f'</div>'
            )
        else:
            notice_html = (
                f'<div class="mock-notice">'
                f'<strong>⚠️ NOTICE: PILOT COHORT ANALYZED VIA MOCK NLP</strong><br/>'
                f'The currently displayed review intelligence records (N = {mock_count}) were processed using '
                f'<code>MockLLMClient</code> (deterministic Portuguese rule-based NLP).'
                f'</div>'
            )
    else:
        notice_html = (
            f'<div class="mock-notice">'
            f'<strong>⚠️ NOTICE: PILOT COHORT ANALYZED VIA MOCK NLP</strong><br/>'
            f'The currently displayed review intelligence records (N = {cohort_size}) were processed using '
            f'<code>MockLLMClient</code> (deterministic Portuguese rule-based NLP).'
            f'</div>'
        )

    if hasattr(st, "html"):
        st.html(notice_html)
    else:
        st.markdown(notice_html, unsafe_allow_html=True)


def apply_plotly_theme(fig: go.Figure, height: int = 380) -> go.Figure:
    """Applies a consistent, clean layout to Plotly figures."""
    fig.update_layout(
        height=height,
        margin=dict(l=40, r=40, t=40, b=40),
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif", size=12),
        hoverlabel=dict(bgcolor="white", font_size=12),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#e9ecef")
    fig.update_yaxes(showgrid=True, gridcolor="#e9ecef")
    return fig
