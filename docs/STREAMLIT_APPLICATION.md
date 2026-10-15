# CommerceLens AI — Streamlit Platform Documentation

## 1. Executive Summary & Purpose

The **CommerceLens AI Streamlit Platform** is a web interface that unifies the four analytical pillars of the platform:
1. **Executive Business Analytics**: Direct queries against the PostgreSQL star schema reflecting verified financial and fulfillment KPIs.
2. **Delivery-Risk Forecaster**: Interactive scenario evaluation powered by the Phase 4 machine learning pipeline (`DeliveryRiskPredictor`) with strict point-in-time feature validation and zero leakage.
3. **Customer Review Sentiment Explorer**: Visualizes Portuguese NLP review intelligence, complaint themes, and fulfillment cohort comparisons, featuring explicit **Mock Analysis Disclosures** for the Phase 5 pilot.
4. **Grounded Analytics Copilot**: An evidence-grounded natural-language analytics assistant governed by an explicit intent allowlist and parameterized SQL templates, strictly forbidding arbitrary LLM-generated SQL.

---

## 2. Architecture & Directory Structure

The application is structured under `src/commercelens/app/`:

```
src/commercelens/app/
├── __init__.py               # Package exports
├── components.py             # UI design system, custom CSS, metric cards, mock alert banners
├── data.py                   # Cached PostgreSQL star-schema queries with grain discipline
├── copilot.py                # Grounded Analytics Copilot engine with intent allowlist
├── main.py                   # Streamlit application entry point and sidebar health checks
└── tabs/
    ├── __init__.py           # Tab package exports
    ├── executive.py          # Tab 1: Executive Business Analytics
    ├── forecaster.py         # Tab 2: Delivery Risk Forecaster
    ├── sentiment.py          # Tab 3: Customer Sentiment Explorer
    └── copilot_tab.py        # Tab 4: Grounded Analytics Copilot
```

---

## 3. Tab Implementations

### Tab 1 — Executive Analytics (`tabs/executive.py`)
- **Data Source**: PostgreSQL star schema views (`v_monthly_sales_performance`, `v_category_merchandise_performance`) and `fact_orders`.
- **Grain Discipline**: Evaluates at `order_id` grain. Pre-aggregates fact tables before joining to prevent Cartesian fan-out.
- **Key Metrics Displayed**:
  - **Delivered GMV**: `R$ 13,221,498.11` (R$ 13.22M)
  - **Delivered Orders**: `96,478` distinct orders (out of 99,441 placed)
  - **Average Order Value (AOV)**: `R$ 137.04`
  - **Freight-to-Merchandise Ratio**: `16.63%`
  - **On-Time Delivery Rate (OTDR)**: `91.89%` (88,643 on-time out of 96,470 SLA-eligible)
  - **Late Delivery Rate (LDR)**: `8.11%` (7,827 late arrivals)
  - **Order Cancellation Rate**: `0.63%` (625 orders)
  - **Unavailable Order Rate**: `0.61%` (609 orders)
- **Interactive Visualizations**:
  - Monthly Delivered GMV and Order Volume (dual-axis bar and line chart, 2016–2018).
  - Top 10 Product Categories by Delivered GMV with Pareto ranking.
  - Top 10 Customer States by Delivered GMV.
  - Complete order lifecycle status distribution table.

### Tab 2 — Delivery Risk Forecaster (`tabs/forecaster.py`)
- **Model Artifact**: `reports/model_artifacts/model_pipeline.joblib` (Regularized Logistic Regression, `C=0.1`, balanced class weights).
- **Point-in-Time Schema**: Uses 27 authorized features available at order checkout.
- **Data Leakage Prevention**: Automatically asserts zero presence of forbidden post-purchase milestone columns (`order_delivered_customer_date`, `carrier_transit_days`, `review_score`, `is_late`, etc.).
- **Evaluation & Limitations Disclosure**:
  - **Validation ROC-AUC**: `0.7902` | **Holdout Test ROC-AUC**: `0.6112`
  - **Holdout Test PR-AUC**: `0.1157` (1.55x lift over 0.0748 base prevalence)
  - **Operational Decision Threshold ($\tau$)**: `0.72`
  - **Holdout Test Recall**: `32.05%` (300 / 936 late orders flagged)
  - **Holdout Test Precision**: `10.37%` (2,593 false alarms)
  - **Temporal Decay Callout**: Prominently discloses the validation-to-test performance decline caused by shifting macro-logistics conditions and the May 2018 nationwide truck drivers' strike.
- **Scenario Testing**: Preset scenarios (Interstate Long-Haul, Local Delivery) and custom parameter sliders. In-memory evaluation with zero persistence of test scenarios to PostgreSQL.

### Tab 3 — Customer Sentiment Explorer (`tabs/sentiment.py`)
- **Data Source**: `fact_review_analysis`, `fact_review_themes`, `view_review_processing_coverage`, and `view_review_delivery_cohort_analysis`.
- **Prominent Mock Notice**: Displays a persistent alert banner indicating that displayed pilot records ($N = 100$) were analyzed using `MockLLMClient` due to unconfigured `GEMINI_API_KEY`.
- **Processing Coverage**:
  - Total Marketplace Reviews: `99,224`
  - Text-Bearing Reviews: `42,697`
  - Completed Pilot Cohort: `100` reviews
- **Visualizations & Insights**:
  - Sentiment Distribution: Positive, Neutral, Negative, Mixed shares.
  - Prevalent Review Themes: Multi-label taxonomy rankings (`delivery_delay`, `product_quality`, `customer_service`, etc.).
  - Delivery Cohort Comparison: Cross-tabulation comparing on-time versus late fulfillment sentiment and delivery-related complaint rates.
- **PII-Safe Explorer**: Masked identifiers (`order_898b...`, `rev_f92a...`), escaped HTML, sentiment and theme filters, and expandable verbatim evidence quotes in Portuguese.

### Tab 4 — Grounded Analytics Copilot (`tabs/copilot_tab.py`)
- **Intent Allowlist**: Restricts natural-language inputs to 8 predefined business intents (`top_categories_gmv`, `delivery_sla_compliance`, `csat_timeliness_gap`, `review_themes_prevalence`, `review_processing_coverage`, `order_status_summary`, `regional_sales_breakdown`, `model_performance_details`).
- **Zero Arbitrary SQL Execution**: The application completely forbids LLM-generated raw SQL. Inquiries are mapped to parameter-bound SQL templates.
- **Operational Badging**: Displays `OFFLINE COPILOT MODE` when `GEMINI_API_KEY` is not present, ensuring users are never misled into believing offline responses originated from Google Gemini.
- **Full Evidence Audit**: Responses include structured text summaries, PostgreSQL data tables, exact SQL code templates, and statistical governance disclaimers.

---

## 4. Local Launch Instructions

### Prerequisites
1. PostgreSQL running locally on port 5432 with `commercelens_db` populated with Phase 1–5 tables and views.
2. Python virtual environment activated with installed project dependencies:
   ```powershell
   pip install -e .
   ```

### Launch Command
Execute the following single command from the project root:
```powershell
streamlit run src/commercelens/app/main.py
```

The application will launch and open automatically in your browser at `http://localhost:8501`.

---

## 5. Security & Performance Governance

1. **Zero Credential Exposure**: Database passwords, hosts, and optional Gemini API keys are loaded strictly from `.env` via `commercelens.config`. No connection strings or secrets are rendered in the UI or written to logs.
2. **Read-Only Data Access**: The application executes read-only `SELECT` statements with row limits (`LIMIT 10` to `LIMIT 50`) and parameterized inputs.
3. **Caching**: Expensive SQL queries are cached using Streamlit's `@st.cache_data(ttl=300)` to optimize response times. Users can manually invalidate cache using the sidebar button.
4. **Untrusted Data Sanitization**: Customer review summaries and verbatim text are escaped using Python's `html.escape` to prevent XSS or prompt-injection exploitation.
