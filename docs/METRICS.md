# CommerceLens AI — Business KPI & Analytical Metrics Framework

> **Status**: Formal mathematical specifications and accounting definitions for CommerceLens AI.  
> **Finalization Notice**: Exact empirical distributions will be calculated and finalized during Phase 1 & Phase 2 data profiling. No statistics or baseline numbers are fabricated.

---

## 1. Core Financial & Commercial KPIs

### 1.1 Gross Merchandise Value (GMV)
- **Definition**: The total transaction monetary volume generated across the marketplace, representing gross item product sales before freight and shipping charges.
- **Formula**:
  $$\text{GMV} = \sum_{i \in \text{Delivered Items}} \text{price}_i$$
- **Numerator**: Sum of `price` from `olist_order_items_dataset` for eligible orders.
- **Denominator**: N/A (Total sum).
- **Inclusion / Exclusion Rules**:
  - Exclude `order_status IN ('canceled', 'unavailable')`.
  - Include all fulfilled / delivered orders.
- **Grain**: Aggregated at order item grain (`order_id, order_item_id`).

### 1.2 Gross Order Value (Total Payment Volume)
- **Definition**: Total money paid by buyers, including product cost and shipping charges.
- **Formula**:
  $$\text{Gross Order Value} = \sum (\text{price} + \text{freight\_value}) = \sum \text{payment\_value}$$
- **Reconciliation Check**:
  $$\sum \text{order\_items.price} + \sum \text{order\_items.freight\_value} \equiv \sum \text{order\_payments.payment\_value}$$
  *(Must hold true within rounding tolerance; exceptions like vouchers or canceled orders flagged in Phase 1).*

### 1.3 Average Order Value (AOV)
- **Definition**: Average gross spend per unique order.
- **Formula**:
  $$\text{AOV} = \frac{\sum \text{Item Price for Delivered Orders}}{\text{Count of Unique Delivered Orders}} = \frac{\text{GMV}}{\text{Distinct Orders}}$$
- **Numerator**: Sum of item prices across delivered orders.
- **Denominator**: `COUNT(DISTINCT order_id)` for delivered orders.

### 1.4 Freight-to-Price Ratio
- **Definition**: Proportion of shipping fee relative to product price, indicating logistics cost burden on buyers.
- **Formula**:
  $$\text{Freight Ratio} = \frac{\sum \text{freight\_value}}{\sum \text{price}}$$
- **Numerator**: Sum of `freight_value`.
- **Denominator**: Sum of `price`.

---

## 2. Logistics & Operational Fulfillment KPIs

### 2.1 On-Time Delivery Rate (OTDR)
- **Definition**: The percentage of successfully delivered orders that arrived at the customer on or before the estimated SLA delivery date.
- **Formula**:
  $$\text{On-Time Delivery Rate} = \frac{\sum \mathbf{1}(\text{order\_delivered\_customer\_date} \le \text{order\_estimated\_delivery\_date})}{\text{Count of Eligible Delivered Orders}} \times 100\%$$
- **Numerator**: `COUNT(order_id)` where `order_delivered_customer_date <= order_estimated_delivery_date` AND `order_status = 'delivered'` AND `order_delivered_customer_date IS NOT NULL`.
- **Denominator (Strict SLA Population)**: `COUNT(order_id)` where `order_status = 'delivered'` AND `order_delivered_customer_date IS NOT NULL` ($N = 96,470$ orders).
- **Strict Exclusion Rule**:
  - Exactly **8 delivered orders** are missing `order_delivered_customer_date`. They are **strictly excluded** from the denominator ($96,478 - 8 = 96,470$) to prevent falsified compliance rates.
  - These 8 orders are audited and tracked separately as `delivered_missing_timestamp_orders`.

### 2.2 Late Delivery Rate (LDR)
- **Definition**: The percentage of successfully delivered orders that arrived strictly after the promised delivery deadline.
- **Formula**:
  $$\text{Late Delivery Rate} = 100\% - \text{On-Time Delivery Rate}$$
  $$\text{LDR} = \frac{\sum \mathbf{1}(\text{order\_delivered\_customer\_date} > \text{order\_estimated\_delivery\_date})}{\text{Count of Eligible Delivered Orders}} \times 100\%$$
- **Denominator**: Same strict SLA population ($N = 96,470$ orders). Missing timestamp delivered orders ($N = 8$) are excluded.

### 2.3 Total Delivery Lead Time (Days)
- **Definition**: Elapsed calendar duration from order purchase to customer receipt.
- **Formula**:
  $$\text{Delivery Lead Time} = \text{EXTRACT(EPOCH FROM (order\_delivered\_customer\_date} - \text{order\_purchase\_timestamp})) / 86400$$
- **Average Lead Time**: $\frac{1}{N} \sum (\text{Delivered Date} - \text{Purchase Date})$.

### 2.4 Carrier Transit Time (Days)
- **Definition**: Duration parcel was in custody of the logistics carrier (Correios).
- **Formula**:
  $$\text{Carrier Transit Time} = (\text{order\_delivered\_customer\_date} - \text{order\_delivered\_carrier\_date})$$
- **Numerator**: Elapsed days between carrier receipt and customer delivery.
- **Denominator**: `COUNT(order_id)` with both timestamps non-null.

### 2.5 Seller Fulfillment Lead Time (Days)
- **Definition**: Duration taken by the merchant to prepare, pack, and hand off parcel to carrier.
- **Formula**:
  $$\text{Seller Lead Time} = (\text{order\_delivered\_carrier\_date} - \text{order\_approved\_at})$$

### 2.6 SLA Estimation Variance (Days)
- **Definition**: Buffer or error between promised delivery date and actual delivery date.
- **Formula**:
  $$\text{SLA Variance} = (\text{order\_estimated\_delivery\_date} - \text{order\_delivered\_customer\_date})$$
  - Positive value: Delivered early (ahead of schedule).
  - Negative value: Delivered late (SLA breached).

---

## 3. Customer Satisfaction & Retention KPIs

### 3.1 Customer Satisfaction (CSAT Proxy)
- **Definition**: Average review rating awarded by customers on a 1-to-5 scale.
- **Formula**:
  $$\text{Average Review Score} = \frac{\sum \text{review\_score}}{\text{Count of Submitted Reviews}}$$
- **Numerator**: Sum of `review_score`.
- **Denominator**: `COUNT(review_id)`.

### 3.2 Review Response Rate
- **Definition**: Proportion of orders where a customer provided a review score.
- **Formula**:
  $$\text{Review Rate} = \frac{\text{Count of Distinct Orders with a Review}}{\text{Total Distinct Orders}} \times 100\%$$

### 3.3 Repeat Customer Rate (Repurchase Rate)
- **Definition**: Percentage of unique human consumers who placed more than 1 order in the marketplace.
- **Formula**:
  $$\text{Repeat Customer Rate} = \frac{\text{Count of Unique Customers with } \ge 2 \text{ Orders}}{\text{Total Distinct Unique Customers}} \times 100\%$$
- **Crucial Grain Note**: Must be computed using `customer_unique_id` (from `olist_customers_dataset`), **never** `customer_id` (which is 1:1 per order).

---

## 4. The Join Fan-Out & Double-Counting Trap

### 4.1 The Problem
In the Olist relational model:
- 1 `order` can have multiple `order_items` ($N$).
- 1 `order` can have multiple `order_payments` ($M$).
- 1 `order` can have multiple `order_reviews` ($K$).

If an analyst naively writes:
```sql
-- DANGEROUS QUERY: INTRODUCES CARTESIAN FAN-OUT
SELECT 
    o.order_id,
    SUM(i.price) AS total_items_price,
    SUM(p.payment_value) AS total_payment
FROM olist_orders_dataset o
JOIN olist_order_items_dataset i ON o.order_id = i.order_id
JOIN olist_order_payments_dataset p ON o.order_id = p.order_id
GROUP BY o.order_id;
```
For an order with 2 items and 2 payments, the query joins $2 \times 2 = 4$ rows!
- `SUM(i.price)` is doubled ($2\times$).
- `SUM(p.payment_value)` is doubled ($2\times$).
This corrupts company GMV, revenue reporting, and financial audits.

### 4.2 The Solution
Pre-aggregate to the `order_id` grain using Common Table Expressions (CTEs) or correlated subqueries before joining:
```sql
-- CORRECT QUERY: GRAIN-ALIGNED CTE AGGREGATION
WITH item_agg AS (
    SELECT 
        order_id,
        SUM(price) AS total_item_price,
        SUM(freight_value) AS total_freight_value,
        COUNT(order_item_id) AS item_count
    FROM olist_order_items_dataset
    GROUP BY order_id
),
payment_agg AS (
    SELECT 
        order_id,
        SUM(payment_value) AS total_payment_value,
        COUNT(payment_sequential) AS payment_slices_count
    FROM olist_order_payments_dataset
    GROUP BY order_id
)
SELECT 
    o.order_id,
    o.order_status,
    COALESCE(i.total_item_price, 0) AS total_item_price,
    COALESCE(i.total_freight_value, 0) AS total_freight_value,
    COALESCE(p.total_payment_value, 0) AS total_payment_value
FROM olist_orders_dataset o
LEFT JOIN item_agg i ON o.order_id = i.order_id
LEFT JOIN payment_agg p ON o.order_id = p.order_id;
```
Every SQL view and Power BI measure in CommerceLens AI strictly enforces this grain alignment.

---

## 5. Operational Exception & Financial Integrity Rules

### 5.1 Cancellation Rate vs. Unavailable Rate
- **Cancellation Rate**:
  $$\text{Cancellation Rate} = \frac{\text{COUNT(order\_id with order\_status = 'canceled')}}{\text{Total Orders placed (99,441)}} \times 100\% = \frac{625}{99,441} \approx 0.628\%$$
- **Unavailable Rate**:
  $$\text{Unavailable Rate} = \frac{\text{COUNT(order\_id with order\_status = 'unavailable')}}{\text{Total Orders placed (99,441)}} \times 100\% = \frac{609}{99,441} \approx 0.612\%$$
- **Reporting Governance**: These two failure modes represent distinct operational breakdowns (buyer/seller remorse cancellation vs merchant inventory stockout). They are reported separately in all SQL views and analytical dashboards.

### 5.2 Zero-Value Voucher Payment Retention
- In `olist_order_payments_dataset`, exactly **9 payment records** have `payment_value = 0.00` (6 vouchers, 3 not_defined).
- **Rule**: Retained in all staging and fact tables (`fact_payments`). Never discarded as "data corruption", preserving transactional sequence numbers and basket coverage proofs.

---

## 6. Power BI DAX Measure Library & Technical Specifications

Every business metric implemented in the Power BI reporting suite (`dashboards/powerbi/dax_measures.dax`) is governed by strict mathematical definitions, explicit grains, and currency formatting in Brazilian Reais (R$):

| DAX Measure | Exact Numerator | Exact Denominator | Grain / Population Filter | DAX Formulation | Baseline Value |
|:---|:---|:---|:---|:---|:---:|
| `Total GMV` | Sum of item `price` | N/A | Delivered orders only | `CALCULATE(SUM(FactOrderItems[price]), FactOrders[order_status] = "delivered")` | R$ 13,221,498.11 |
| `Total Freight` | Sum of item `freight_value` | N/A | Delivered orders only | `CALCULATE(SUM(FactOrderItems[freight_value]), FactOrders[order_status] = "delivered")` | R$ 2,198,275.64 |
| `Delivered Orders` | Count of distinct `order_id` | N/A | Delivered orders only | `CALCULATE(DISTINCTCOUNT(FactOrders[order_id]), FactOrders[order_status] = "delivered")` | 96,478 orders |
| `AOV` | `[Total GMV]` | `[Delivered Orders]` | Delivered orders | `DIVIDE([Total GMV], [Delivered Orders], BLANK())` | R$ 137.04 |
| `SLA-Eligible Orders` | Count of distinct `order_id` | N/A | Delivered orders with non-null `order_delivered_customer_date` | `CALCULATE(DISTINCTCOUNT(FactOrders[order_id]), FactOrders[is_eligible_for_sla] = TRUE())` | 96,470 orders |
| `Delivered Missing Timestamps` | Count of distinct `order_id` | N/A | Delivered orders with null `order_delivered_customer_date` | `CALCULATE(DISTINCTCOUNT(FactOrders[order_id]), FactOrders[order_status] = "delivered", ISBLANK(FactOrders[order_delivered_customer_date]))` | 8 orders |
| `On-Time Orders` | Count of distinct `order_id` | N/A | SLA-eligible and delivered on/before SLA | `CALCULATE([Total Orders], FactOrders[is_eligible_for_sla] = TRUE(), FactOrders[is_late] = FALSE())` | 88,644 orders |
| `Late Orders` | Count of distinct `order_id` | N/A | SLA-eligible and delivered after SLA | `CALCULATE([Total Orders], FactOrders[is_eligible_for_sla] = TRUE(), FactOrders[is_late] = TRUE())` | 7,826 orders |
| `On-Time Delivery Rate` | `[On-Time Orders]` | `[SLA-Eligible Orders]` | SLA-eligible delivered orders | `DIVIDE([On-Time Orders], [SLA-Eligible Orders], BLANK())` | 91.89% |
| `Late Delivery Rate` | `[Late Orders]` | `[SLA-Eligible Orders]` | SLA-eligible delivered orders | `DIVIDE([Late Orders], [SLA-Eligible Orders], BLANK())` | 8.11% |
| `Average Review Score` | Sum of `review_score` | Count of submitted reviews | Submitted reviews ($N = 99,224$) | `AVERAGE(FactReviews[review_score])` | 4.09 stars |
| `On-Time Order CSAT` | Sum of `review_score` | Count of on-time reviews | On-time cohort reviews ($N = 88,653$) | `CALCULATE([Average Review Score], FactOrders[is_eligible_for_sla] = TRUE(), FactOrders[is_late] = FALSE())` | 4.29 stars |
| `CSAT Delivery Penalty` | `[Late Order CSAT]` - `[On-Time Order CSAT]` | N/A | Negative satisfaction drop (unrounded averages: 2.566 - 4.294) | `[Late Order CSAT] - [On-Time Order CSAT]` | -1.73 stars |
| `CSAT Timeliness Gap` | `[On-Time Order CSAT]` - `[Late Order CSAT]` | N/A | Positive satisfaction premium (unrounded averages: 4.294 - 2.566) | `[On-Time Order CSAT] - [Late Order CSAT]` | +1.73 stars |
| `Total Unique Customers` | Count of distinct `customer_unique_id` | N/A | Persistent human consumers | `DISTINCTCOUNT(DimCustomers[customer_unique_id])` | 96,096 |
| `Repeat Customers Count` | Unique consumers with $\ge 2$ orders | N/A | Repeat buyer filter | `COUNTROWS(FILTER(VALUES(DimCustomers[customer_unique_id]), CALCULATE(DISTINCTCOUNT(FactOrders[order_id])) > 1))` | 2,997 |
| `Repeat Customer Rate` | `[Repeat Customers Count]` | `[Total Unique Customers]` | Unique consumer population | `DIVIDE([Repeat Customers Count], [Total Unique Customers], BLANK())` | 3.12% |
| `Delivered Orders (Category)` | Count of distinct `FactOrderItems[order_id]` | N/A | Category grain with delivered filter | `CALCULATE(DISTINCTCOUNT(FactOrderItems[order_id]), FactOrders[order_status] = "delivered")` | Category-specific |
| `Active Sellers` | Distinct `FactOrderItems[seller_key]` | N/A | Merchants with $\ge 1$ delivered order | `CALCULATE(DISTINCTCOUNT(FactOrderItems[seller_key]), FactOrders[order_status] = "delivered")` | 2,970 sellers |
| `Total Sellers` | Distinct `DimSellers[seller_key]` | N/A | All registered merchants in catalog | `DISTINCTCOUNT(DimSellers[seller_key])` | 3,095 sellers |

### 6.1 CSAT Discrepancy Reconciliation & Historical Cohort Audit (2.26 vs. 2.57 stars)

A forensic audit of customer review scores across the relational schema resolves the historical reporting variance between exploratory SQL analytics (~2.26 stars) and Power BI production reporting (2.57 stars):

1. **Production Pipeline & Power BI Definition (Timestamp SLA Breach)**:
   - **Condition**: `fo.is_eligible_for_sla = TRUE AND fo.is_late = TRUE` where `is_late` is defined strictly by timestamp comparison (`order_delivered_customer_date > order_estimated_delivery_date`).
   - **Review Population**: Exactly **7,700 reviews** across 7,661 unique late orders.
   - **Mean CSAT**: Exactly **2.5665 stars** (published as **2.57 stars**).
   - **1-Star Share**: 46.16% (3,554 reviews).

2. **Historical Phase 2A Exploratory Query (Calendar-Day Truncation Delay)**:
   - **Condition**: `order_delivered_customer_date::DATE > order_estimated_delivery_date::DATE` (orders arriving $\ge 1$ full calendar day late).
   - **Review Population**: Exactly **6,409 reviews** across 6,380 unique orders.
   - **Mean CSAT**: Exactly **2.2710 stars** (published historically as **~2.26 – 2.27 stars**).
   - **1-Star Share**: 53.74% (3,444 reviews, reconciling the historical "~54% 1-star feedback" observation).

3. **The Same-Day Afternoon Fulfillment Cohort ($N = 1,291$)**:
   - Because Olist timestamps `order_estimated_delivery_date` at midnight (`00:00:00`), packages delivered between 12:01 AM and 11:59 PM on the promised date breach the timestamp SLA, but arrive on the promised calendar day from the buyer's perspective.
   - **Review Population**: Exactly **1,291 reviews**.
   - **Mean CSAT**: **4.03 stars** (strong positive satisfaction).
   - **Mathematical Reconciliation**: $6,409 \text{ (calendar-day late)} + 1,291 \text{ (same-day late)} = 7,700 \text{ late reviews}$.
   - Weighted Average: $\frac{(6,409 \times 2.2710) + (1,291 \times 4.0333)}{7,700} = \mathbf{2.5665} \to \mathbf{2.57 \text{ stars}}$.

4. **Complete Review Population Accounting ($N = 99,224$)**:
   - On-Time Orders (`is_eligible_for_sla = TRUE AND is_late = FALSE`): **88,653 reviews** (4.29 stars)
   - Late Orders (`is_eligible_for_sla = TRUE AND is_late = TRUE`): **7,700 reviews** (2.57 stars)
   - Undelivered / In-Transit (`is_delivered = FALSE`): **2,863 reviews** (1.75 stars)
   - Delivered Missing Milestone (`is_delivered = TRUE AND order_delivered_customer_date IS NULL`): **8 reviews** (4.50 stars)
   - **Total Verified**: $88,653 + 7,700 + 2,863 + 8 = \mathbf{99,224 \text{ reviews}}$ (100.0% reconciled).

---

## 7. Phase 5: NLP & Customer Review Intelligence Metrics

Review intelligence metrics bridge unstructured Brazilian Portuguese feedback with relational business performance:

| Metric Name | Business Definition | Exact Numerator | Exact Denominator | Population & Exclusions | Baseline Value |
|:---|:---|:---|:---|:---|:---:|
| `Text-Bearing Reviews` | Reviews containing non-empty comment title or message | Count of distinct reviews with non-blank title or message | N/A | Excludes reviews with empty/null comments | **42,697 reviews** (43.03%) |
| `Reviews without Text` | Reviews submitted with star rating only (no written feedback) | Count of distinct reviews with blank/null title and message | N/A | Rating-only feedback | **56,527 reviews** (56.97%) |
| `Review Text Coverage %` | Share of total marketplace reviews bearing customer commentary | `[Text-Bearing Reviews]` | `[Total Reviews]` ($99,224$) | Total review population | **43.03%** |
| `Text Sentiment Negative %` | Share of analyzed reviews classified with negative sentiment | Count of analyzed reviews with `sentiment_label = 'negative'` | Count of analyzed reviews | Text-bearing analyzed cohort | **11.00%** (pilot $N=100$) |
| `Text Sentiment Positive %` | Share of analyzed reviews classified with positive sentiment | Count of analyzed reviews with `sentiment_label = 'positive'` | Count of analyzed reviews | Text-bearing analyzed cohort | **57.00%** (pilot $N=100$) |
| `Delivery Complaint Share %` | Share of analyzed reviews discussing delivery issues | Count of analyzed reviews with `delivery_related = TRUE` | Count of analyzed reviews | Text-bearing analyzed cohort | **37.00%** (pilot $N=100$) |
| `Rating Proxy Concordance %` | Agreement rate between text sentiment and rating score proxy | Direct agreement matches between text sentiment and rating proxy | Total compared text reviews | Excludes reviews without text | **60.00%** (pilot $N=100$) |

### 7.1 Rating Sentiment Proxy Definition
- **Scores 1–2**: `Negative Rating Proxy`
- **Score 3**: `Neutral Rating Proxy`
- **Scores 4–5**: `Positive Rating Proxy`

> [!NOTE]
> **Analytical Governance**: The rating proxy is an operational baseline, not ground truth. Customers frequently write nuanced or multi-aspect feedback (e.g. 5 stars praising product quality while noting slow shipping) that ratings alone cannot capture.
