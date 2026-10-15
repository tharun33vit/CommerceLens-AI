"""
CommerceLens AI — Grounded Analytics Copilot Tab
================================================
Safe, evidence-grounded conversational analytics copilot.
Enforces an explicit intent allowlist, parameterized SQL templates,
zero arbitrary SQL execution, and transparent offline/live Gemini badging.
"""

from typing import Optional
import streamlit as st

from commercelens.app.copilot import APPROVED_INTENTS, GroundedAnalyticsCopilot


@st.cache_resource(show_spinner=False)
def get_cached_copilot() -> GroundedAnalyticsCopilot:
    """Instantiates and caches the Grounded Analytics Copilot."""
    return GroundedAnalyticsCopilot()


def render_copilot_tab() -> None:
    """Renders Tab 4: Grounded Analytics Copilot."""
    st.markdown("### 🤖 Grounded Analytics Copilot")
    st.markdown(
        "Ask natural-language business and operational questions. The Copilot answers solely using "
        "predefined, approved SQL views and verified metric definitions. "
        "**Unrestricted arbitrary SQL generation is strictly prohibited.**"
    )

    copilot = get_cached_copilot()

    # 1. Operational Mode Indicator Banner
    if copilot.is_live_gemini:
        banner_html = (
            '<div style="background-color: #d1e7dd; border-left: 5px solid #198754; padding: 10px 14px; border-radius: 4px; margin-bottom: 14px; color: #0f5132; font-size: 0.88rem;">'
            '<strong>🟢 GEMINI-GROUNDED MODE</strong>: Live Google Gemini configured via <code>GEMINI_API_KEY</code>. '
            'Inferences are constrained strictly to validated SQL view outputs.'
            '</div>'
        )
    else:
        banner_html = (
            '<div style="background-color: #e2e3e5; border-left: 5px solid #6c757d; padding: 10px 14px; border-radius: 4px; margin-bottom: 14px; color: #383d41; font-size: 0.88rem;">'
            '<strong>⚪ OFFLINE COPILOT MODE</strong>: <code>GEMINI_API_KEY</code> is not configured. '
            'The copilot operates using deterministic intent classification and verified PostgreSQL query execution. '
            'Zero external API calls are made.'
            '</div>'
        )
    if hasattr(st, "html"):
        st.html(banner_html)
    else:
        st.markdown(banner_html, unsafe_allow_html=True)

    # 2. Suggested Starter Questions
    st.markdown("#### Suggested Verified Questions:")
    sample_queries = [
        "Which product categories generate the highest delivered GMV?",
        "What is the marketplace on-time delivery rate (OTDR)?",
        "How do customer review scores differ between on-time and late deliveries?",
        "Which customer review themes occur most frequently?",
        "How many reviews have been processed in the NLP pilot?",
        "What is the distribution of orders across lifecycle statuses?",
        "Which Brazilian states have the highest sales volume?",
        "What are the holdout performance metrics of the Phase 4 ML model?",
    ]

    # Initialize chat query state
    if "copilot_query" not in st.session_state:
        st.session_state["copilot_query"] = sample_queries[0]

    cols = st.columns(4)
    for idx, q_text in enumerate(sample_queries):
        col_idx = idx % 4
        with cols[col_idx]:
            if st.button(q_text, key=f"sq_{idx}", use_container_width=True):
                st.session_state["copilot_query"] = q_text

    st.markdown("---")

    # 3. User Query Form
    with st.form("copilot_query_form"):
        user_input = st.text_input(
            "Enter your analytics question:",
            value=st.session_state.get("copilot_query", sample_queries[0]),
            placeholder="e.g., What is the on-time delivery rate?",
        )
        submit_btn = st.form_submit_button("🔍 Ask Copilot", type="primary", use_container_width=True)

    # 4. Process and Display Response
    if submit_btn or st.session_state.get("copilot_query"):
        q_to_run = user_input.strip() if submit_btn else st.session_state["copilot_query"]
        with st.spinner("Analyzing verified metrics..."):
            response = copilot.answer_question(q_to_run)

        st.markdown("---")
        st.markdown(f"### 💡 Answer ({response['mode']})")

        if response["success"]:
            # Structured Answer Header rendered natively with full Markdown formatting
            with st.container(border=True):
                st.markdown(f"#### 📌 {response['title']}")
                st.markdown(response["summary"])

            # Tabular Evidence Data
            if response["data"] is not None and not response["data"].empty:
                st.markdown("#### Retrieved Evidence Data (PostgreSQL)")
                st.dataframe(response["data"], use_container_width=True, hide_index=True)

            # SQL Governance & View Provenance Audit
            with st.expander("🛡️ Verified SQL Template & Grain Provenance", expanded=False):
                st.markdown(f"**Relational Source / View**: `{response['view']}`")
                st.markdown(f"**Declared Grain**: `{response['grain']}`")
                st.code(response["sql"], language="sql")

            # Evidence & Statistical Caveat
            st.info(f"ℹ️ **Statistical Governance**: {response['caveat']}")

        else:
            # Safe Rejection Message
            st.error("🚫 Question Outside Allowlist Policy")
            st.markdown(response["answer"])

    # 5. Allowlist Policy Information
    with st.expander("📋 Governance Policy: Approved Business Intents Allowlist"):
        st.markdown(
            "CommerceLens AI enforces zero arbitrary SQL execution. Every natural-language inquiry is strictly mapped "
            "to one of the following validated business analytics templates:"
        )
        for intent_id, info in APPROVED_INTENTS.items():
            st.markdown(f"- **{info['title']}** (`{intent_id}`): {info['description']} *(View: `{info['view']}`, Grain: `{info['grain']}`)*")
