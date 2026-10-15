"""
CommerceLens AI — Streamlit Platform Entry Point
================================================
Production-grade e-commerce analytics, machine learning delivery risk forecasting,
Portuguese customer review intelligence, and grounded analytics copilot.

Usage:
    streamlit run src/commercelens/app/main.py
"""

import os
from pathlib import Path
import streamlit as st

# Configure page settings before any other Streamlit commands
st.set_page_config(
    page_title="CommerceLens AI — E-Commerce Analytics Platform",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from commercelens.app.components import inject_custom_css
from commercelens.app.data import check_db_health, get_review_model_breakdown
from commercelens.app.tabs import (
    render_copilot_tab,
    render_executive_tab,
    render_forecaster_tab,
    render_sentiment_tab,
)


def main() -> None:
    """Main application routine."""
    # Inject design system CSS
    inject_custom_css()

    # --------------------------------------------------------------------------
    # Sidebar: System Health, Provenance & Navigation Controls
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("## 🛍️ CommerceLens AI")
        st.caption("Brazilian E-Commerce (Olist) Intelligence Platform")
        st.markdown("---")

        # 1. System Health Checks
        st.markdown("### 🖥️ Platform Health")
        
        # PostgreSQL check
        db_ok, db_msg = check_db_health()
        if db_ok:
            st.markdown("🟢 **PostgreSQL Star Schema**: Active")
        else:
            st.markdown(f"🔴 **PostgreSQL**: Disconnected ({db_msg})")
            st.warning("Ensure PostgreSQL is running locally on port 5432.")

        # ML Model Artifact check
        model_file = Path("reports/model_artifacts/model_pipeline.joblib")
        if model_file.is_file():
            st.markdown("🟢 **Phase 4 ML Model**: Available (LR)")
        else:
            st.markdown("🔴 **Phase 4 ML Model**: Missing artifact")

        # Grounded Analytics Copilot check (vetted parameterized SQL views)
        st.markdown("🟢 **Copilot Engine**: SQL-Grounded (Vetted Views)")

        model_counts = get_review_model_breakdown() if db_ok else {}
        mock_cnt = sum(v for k, v in model_counts.items() if "mock" in k.lower())
        flash_38_cnt = sum(v for k, v in model_counts.items() if "3.8" in k.lower())
        flash_lite_cnt = sum(v for k, v in model_counts.items() if "3.5" in k.lower() or "lite" in k.lower())
        gemini_cnt = flash_38_cnt + flash_lite_cnt

        if gemini_cnt > 0 and mock_cnt > 0:
            st.markdown(f"🟢 **Review NLP Status**: Multi-Cohort Pilot (Mock: {mock_cnt}, Gemini: {gemini_cnt})")
        elif gemini_cnt > 0:
            st.markdown(f"🟢 **Review NLP Status**: Live Gemini Pilot (N = {gemini_cnt})")
        else:
            st.markdown(f"⚠️ **Review NLP Status**: Mock Pilot (N = {mock_cnt or 100})")

        st.markdown("---")

        # 2. Global Filters (where applicable to Tab 1)
        st.markdown("### 🔍 Dashboard Filters")
        selected_state = st.selectbox(
            "Customer State (Tab 1):",
            [
                "All", "SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "ES",
                "GO", "PE", "CE", "PA", "MT", "MA", "MS", "PB", "PI", "RN",
                "AL", "SE", "TO", "RO", "AM", "AC", "AP", "RR",
            ],
            index=0,
            help="Filters Tab 1 Executive Analytics by customer delivery state.",
        )

        st.markdown("---")

        # 3. Cache Management
        if st.button("🔄 Refresh Data Cache", use_container_width=True):
            st.cache_data.clear()
            st.success("Query cache cleared successfully.")

        st.markdown("---")
        st.markdown(
            "<div style='font-size: 0.75rem; color: #6c757d;'>"
            "CommerceLens AI v0.1.0<br/>"
            "Phase 6: Streamlit & Grounded Copilot<br/>"
            "Dataset: Olist Historical (2016–2018)"
            "</div>",
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------------------------
    # Main Tabs
    # --------------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Executive Analytics",
        "🚚 Delivery Risk Forecaster",
        "💬 Review Sentiment Explorer",
        "🤖 Grounded Analytics Copilot",
    ])

    with tab1:
        render_executive_tab(selected_state=selected_state)

    with tab2:
        render_forecaster_tab()

    with tab3:
        render_sentiment_tab()

    with tab4:
        render_copilot_tab()


if __name__ == "__main__":
    main()
