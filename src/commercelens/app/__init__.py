"""
Streamlit Web Application Module
================================
Implements interactive dashboards, scenario calculators, ML risk scoring UI,
and the Natural Language Analytics Copilot chat interface.
"""

from .components import (
    apply_plotly_theme,
    format_currency_decimal,
    format_freight_subtitle,
    format_percentage_safe,
    metric_card,
    render_mock_notice,
)
from .copilot import APPROVED_INTENTS, GroundedAnalyticsCopilot
from .data import check_db_health, get_executive_kpis

__all__ = [
    "apply_plotly_theme",
    "format_currency_decimal",
    "format_freight_subtitle",
    "format_percentage_safe",
    "metric_card",
    "render_mock_notice",
    "APPROVED_INTENTS",
    "GroundedAnalyticsCopilot",
    "check_db_health",
    "get_executive_kpis",
]
