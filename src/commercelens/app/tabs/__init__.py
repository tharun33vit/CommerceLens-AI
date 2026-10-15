"""
CommerceLens AI — Streamlit Tab Modules
=======================================
Modular presentation layer for:
- Executive Analytics
- Delivery Risk Forecaster
- Customer Sentiment Explorer
- Grounded Analytics Copilot
"""

from .executive import render_executive_tab
from .forecaster import render_forecaster_tab
from .sentiment import render_sentiment_tab
from .copilot_tab import render_copilot_tab

__all__ = [
    "render_executive_tab",
    "render_forecaster_tab",
    "render_sentiment_tab",
    "render_copilot_tab",
]
