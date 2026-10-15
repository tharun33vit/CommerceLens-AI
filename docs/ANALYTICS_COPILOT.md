# CommerceLens AI — Grounded Analytics Copilot Technical Specification

## 1. Safety Architecture & Governance Principles

The **CommerceLens Grounded Analytics Copilot** delivers evidence-grounded natural-language question answering for e-commerce business analytics.

Traditional LLM analytics assistants often generate free-form SQL or calculate numbers from generative assumptions. This introduces severe vulnerabilities:
- **Hallucinations**: Generative models frequently invent table joins, column names, or incorrect mathematical formulas.
- **SQL Injection**: Malicious user inputs can hijack LLM-generated queries to drop tables, exfiltrate credentials, or bypass security rules.
- **Cartesian Fan-Out & Double Counting**: Joining one-to-many tables (such as order items and payments) without pre-aggregation produces massive revenue corruption.

### Cardinal Engineering Rules for the Copilot
1. **Zero Arbitrary SQL Execution**: The Copilot **never** executes unrestricted LLM-generated SQL directly against PostgreSQL.
2. **Strict Intent Allowlist**: Inquiries are mapped strictly to an approved set of verified business intents with pre-vetted SQL templates.
3. **Evidence Grounding**: Every answer must present the actual database query results, declared table grain, and SQL template snippet.
4. **Transparent Operating Badges**: When `GEMINI_API_KEY` is omitted, the copilot explicitly runs in `OFFLINE COPILOT MODE`. It never fabricates answers or claims an offline response was produced by Google Gemini.

---

## 2. Intent Allowlist Specification

The Copilot maintains an explicit dictionary of supported business analytics intents (`APPROVED_INTENTS`):

| Intent ID | Title | Relational View / Source | Declared Grain | Description |
| :--- | :--- | :--- | :--- | :--- |
| `top_categories_gmv` | Top Categories by GMV | `v_category_merchandise_performance` | 1 row per Category Name | Ranked by delivered GMV and cumulative Pareto share. |
| `delivery_sla_compliance` | Delivery SLA Compliance | `v_delivery_sla_operations` | Marketplace Aggregate | On-Time Delivery Rate (OTDR), Late Delivery Rate (LDR), and lead times. |
| `csat_timeliness_gap` | CSAT Satisfaction Gap | `v_csat_and_delivery_correlation` | 1 row per Fulfillment Category | Comparison of review scores between on-time vs late delivery cohorts. |
| `review_themes_prevalence` | Customer Review Themes | `fact_review_themes` | 1 row per Taxonomy Theme | Frequency of complaint and praise themes in customer reviews. |
| `review_processing_coverage` | Review Processing Coverage | `view_review_processing_coverage` | Pipeline Audit Aggregate | Reviews with text, without text, and pipeline completion status. |
| `order_status_summary` | Order Lifecycle Status | `fact_orders` | 1 row per Order Status | Distribution of orders across delivered, canceled, unavailable, etc. |
| `regional_sales_breakdown` | Regional Sales & States | `fact_orders JOIN dim_customers` | 1 row per Customer State | Delivered GMV and order counts across Brazilian states. |
| `model_performance_details` | Phase 4 Model Evaluation | `reports/model_artifacts/metrics.json` | Holdout Test (N = 12,507) | ROC-AUC, PR-AUC, precision, recall, and temporal drift analysis. |

---

## 3. Query Execution Lifecycle

```
[ User Natural Language Question ]
               │
               ▼
   [ 1. Sanitization & Anti-Injection Guard ] ──► (Contains DROP/DELETE/--?) ──► REJECT IMMEDIATELY
               │
               ▼
   [ 2. Deterministic / Intent Scoring ] ──► (Matches allowlist keywords?) ──► REJECT IF UNSUPPORTED
               │ (Intent Approved)
               ▼
   [ 3. Parameterized SQL Template Selection ]
               │
               ▼
   [ 4. Read-Only PostgreSQL Execution ] (Enforces statement timeouts & row limits)
               │
               ▼
   [ 5. Evidence Synthesis & Formatting ]
               │
               ▼
[ Grounded Answer + Data Table + SQL Code + Statistical Caveats ]
```

---

## 4. LLM Fallback & Security Protocol

- **Offline Mode (`GEMINI_API_KEY` absent)**:
  - Uses deterministic keyword matching against the intent allowlist.
  - Retrieves data directly from the PostgreSQL engine.
  - Synthesizes formatted evidence responses using pre-defined reporting templates.
  - Labels the output as `OFFLINE COPILOT MODE`.
- **Live Gemini Mode (`GEMINI_API_KEY` configured)**:
  - Invocations are strictly limited to intent classification and evidence summarization.
  - The model prompt is provided with the already-executed query output schema, never database passwords or raw connection strings.
  - Zero arbitrary SQL generation is permitted.
  - Labels the output as `GEMINI-GROUNDED MODE`.

---

## 5. Statistical Governance & Disclaimers

Every Copilot response returns an explicit statistical governance caveat:
> *"Evidence Grounding: Figures are retrieved directly from PostgreSQL star-schema views without extrapolation. Statistical association between delivery delays and customer ratings does not establish direct sole causation."*
