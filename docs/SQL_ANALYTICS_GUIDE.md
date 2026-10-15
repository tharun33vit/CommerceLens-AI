# CommerceLens AI — SQL Analytics & Semantic Layer Guide

> **Module**: Relational SQL Analytics, CTE Architectures & Semantic Reporting Views  
> **Status**: Interview-Defensible Query Suite & Business KPI Specifications  
> **Target Audience**: Data Analysts, Analytics Engineers, Business Intelligence Developers

---

## 1. Overview of Analytical Capabilities

The SQL analytics layer provides a production-grade, mathematically verified analytical foundation for CommerceLens AI. It enforces:
- **Strict Grain Discipline**: No multi-item or multi-payment joining without CTE pre-aggregation.
- **Advanced SQL Patterns**: Window functions (`LAG`, `DENSE_RANK`, `RANK`, `NTILE`), CTEs, rolling 3-month moving averages, cumulative Pareto distributions, and conditional aggregations.
- **Accurate Metric Labeling**: Distinguishing **Item Merchandise Value (GMV)** from accounting recognized revenue, isolating freight value, and separating payment collections.
- **Audited Data Realities**: Isolating the 8 delivered orders with missing delivery timestamps, retaining 9 zero-value vouchers, and distinguishing 96,096 persistent customers from 99,441 checkout tokens.

---

## 2. Analytical Views Catalogue (`sql/views/01_analytical_views.sql`)

The semantic views provide verified data abstractions for downstream consumers (Power BI dashboards, Streamlit reporting, and query-bounded LLM Copilot retrieval).

| View Name | Primary Business Grain | Description & Techniques | Key Output Metrics |
|:---|:---|:---|:---|
| `v_monthly_sales_performance` | Calendar Year-Month | Monthly sales velocity, distinct order counts, AOV, and MoM GMV growth rate using `LAG()`. | `delivered_item_merchandise_value`, `delivered_orders_count`, `aov_delivered`, `mom_gmv_growth_pct` |
| `v_category_merchandise_performance` | Product Category (English) | Category sales ranking via `DENSE_RANK()`, average SKU price, freight-to-price ratio, and cumulative Pareto % via window frames. | `revenue_rank`, `total_item_merchandise_value`, `freight_to_price_ratio_pct`, `cumulative_gmv_pct` |
| `v_delivery_sla_operations` | Marketplace Summary | Operational fulfillment, milestone lead times, and strict On-Time Delivery Rate (OTDR) excluding the 8 missing timestamp orders. | `sla_eligible_delivered_orders`, `delivered_missing_timestamp_orders`, `on_time_delivery_rate_pct`, `avg_delivery_lead_time_days` |
| `v_customer_repurchase_rfm` | `customer_unique_id` | Persistent customer intelligence distinguishing transient checkout sessions from unique consumers; tracks repeat purchase flags. | `total_orders_placed`, `total_customer_ltd_gmv`, `customer_relationship_span_days`, `is_repeat_buyer` |
| `v_csat_and_delivery_correlation` | Fulfillment SLA Category | Evaluates customer satisfaction (CSAT) ratings and negative review rates across On-Time vs Late vs Non-Delivered orders. | `fulfillment_category`, `avg_review_score`, `negative_review_pct`, `five_star_pct` |
| `v_reconciliation_audit` | Metric Name | Live financial audit comparing `fact_orders` totals against `fact_order_items` and `fact_payments` line sums. | `reported_value`, variance verification |

---

## 3. Query Suite Walkthrough & Interview Talking Points

### 3.1 Script 1: Sales and Order Performance (`sql/analysis/01_kpi_sales_and_orders.sql`)
- **Key Techniques**:
  - `LAG(delivered_gmv, 1) OVER (ORDER BY year, month)` to calculate Month-over-Month (MoM) GMV growth without self-joins.
  - `AVG(delivered_gmv) OVER (ORDER BY year, month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` for rolling 3-month trend smoothing.
  - `DENSE_RANK() OVER (ORDER BY total_item_merchandise_value DESC)` for category ranking with `HAVING COUNT(*) >= 50` statistical threshold.
  - `NTILE(4) OVER (ORDER BY total_seller_gmv DESC)` to analyze marketplace seller concentration into performance quartiles.
- **Interview Defense**:
  *Why use DENSE_RANK over RANK?* In financial category rankings, ties should not skip subsequent ranks, ensuring clean indexing for reporting.
  *Why apply HAVING >= 50?* Small-volume categories (e.g., 2 items sold) exhibit extreme variance in average price and freight ratios, creating misleading "bottom" performers.

### 3.2 Script 2: Delivery Operations and SLA Performance (`sql/analysis/02_delivery_operations_and_sla.sql`)
- **Key Techniques**:
  - Strict denominator filter: `WHERE is_eligible_for_sla = TRUE` (96,470 orders).
  - Milestone decomposition:
    - **Seller Dispatch Duration**: `order_delivered_carrier_date - order_approved_at`.
    - **Carrier Transit Duration**: `order_delivered_customer_date - order_delivered_carrier_date`.
    - **Total Lead Time**: `order_delivered_customer_date - order_purchase_timestamp`.
  - State-to-State Logistics Corridor Analysis: Ranks origin-to-destination corridors (e.g., SP -> RJ vs SP -> BA) by delay risk using `RANK()` with a minimum sample size of 250 orders.
- **Interview Defense**:
  *Why are 8 delivered orders excluded from SLA calculations?* In Olist, 8 orders have status `delivered` but `order_delivered_customer_date` is NULL. Imputing 0 days would falsely inflate on-time compliance; imputing estimated delivery would fabricate actual performance. Excluding them while reporting them in a dedicated audit counter preserves statistical truthfulness.

### 3.3 Script 3: Customer Intelligence and RFM (`sql/analysis/03_customer_intelligence_and_rfm.sql`)
- **Key Techniques**:
  - Aggregating by `customer_unique_id` (96,096 consumers) rather than `customer_id` (99,441 checkout tokens).
  - Categorizing loyalty segments: 1 order (One-Time Buyer, ~96.9%), 2 orders (Repeat Buyer, ~2.8%), 3+ orders (Loyal/Power Buyer, ~0.3%).
  - Correlating delivery timeliness with review scores: Demonstrating a strong empirical negative association between late delivery and customer sentiment (observational correlation, not unconfounded causality). In the production dimensional model (`fact_orders.is_late` based on timestamp comparison `order_delivered_customer_date > order_estimated_delivery_date`), late deliveries average **2.57 stars** ($N = 7,700$ reviews across 7,661 orders) versus **4.29 stars** for on-time orders ($N = 88,653$ reviews across 88,163 orders), representing a **-1.72 star delivery penalty**. When evaluated by strict calendar-day truncation (`delivered_date::DATE > estimated_date::DATE`, filtering out the 1,291 afternoon deliveries arriving on the promised calendar day whose CSAT is 4.03 stars), delayed orders average **2.27 stars** ($N = 6,409$ reviews), with 1-star reviews accounting for 53.74% (~54%) of feedback compared to 6.60% for on-time deliveries.
- **Interview Defense**:
  *Why does Olist have two customer ID columns?* `customer_id` is an anonymized checkout token generated per purchase session. `customer_unique_id` is the hashed national consumer identifier. Measuring customer lifetime value or churn on `customer_id` would erroneously conclude that 100% of customers are single-order buyers.

### 3.4 Script 4: Operational Quality & Anti-Fan-Out Proof (`sql/analysis/04_operational_quality_and_reconciliation.sql`)
- **Key Techniques**:
  - Side-by-side demonstration of naive unaggregated join vs CTE pre-aggregation on multi-item and multi-payment orders.
  - Complete financial reconciliation verifying that `fact_orders` sums equal line item and payment sums with exact **0.00 variance**.
  - Referential integrity audit asserting zero orphaned foreign keys across the entire star schema.
  - Verification that the 9 zero-value voucher payments remain intact.
- **Interview Defense**:
  *What is join fan-out and how did you prevent it?* Joining multi-item orders ($N$ items) with multi-payment orders ($M$ payments) creates $N \times M$ rows. Calculating `SUM(price)` multiplies the merchandise value by $M$, while `SUM(payment_value)` multiplies payments by $N$. In CommerceLens AI, fact tables maintain strict single grains, and `fact_orders` rolls up items and payments in isolated CTEs before joining.

---

## 4. Execution Commands

```bash
# Execute analytical query suites using psql
psql -U postgres -d commercelens_db -f sql/analysis/01_kpi_sales_and_orders.sql
psql -U postgres -d commercelens_db -f sql/analysis/02_delivery_operations_and_sla.sql
psql -U postgres -d commercelens_db -f sql/analysis/03_customer_intelligence_and_rfm.sql
psql -U postgres -d commercelens_db -f sql/analysis/04_operational_quality_and_reconciliation.sql
```
