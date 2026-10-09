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
  $$\text{On-Time Delivery Rate} = \frac{\sum \mathbf{1}(\text{order\_delivered\_customer\_date} \le \text{order\_estimated\_delivery\_date})}{\text{Count of Orders with Confirmed Delivery}} \times 100\%$$
- **Numerator**: `COUNT(order_id)` where `order_delivered_customer_date <= order_estimated_delivery_date` AND `order_status = 'delivered'`.
- **Denominator**: `COUNT(order_id)` where `order_delivered_customer_date IS NOT NULL` AND `order_status = 'delivered'`.
- **Exclusion**: In-transit, canceled, or unavailable orders without a delivery timestamp are excluded from the denominator.

### 2.2 Late Delivery Rate (LDR)
- **Definition**: The percentage of successfully delivered orders that arrived strictly after the promised delivery deadline.
- **Formula**:
  $$\text{Late Delivery Rate} = 100\% - \text{On-Time Delivery Rate}$$
  $$\text{LDR} = \frac{\sum \mathbf{1}(\text{order\_delivered\_customer\_date} > \text{order\_estimated_delivery\_date})}{\text{Count of Orders with Confirmed Delivery}} \times 100\%$$

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
