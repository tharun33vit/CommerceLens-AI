# CommerceLens AI — Machine Learning Feature Dictionary

> **Point-in-Time Constraint**: Every feature used in the delivery-risk model is strictly available at the moment of order placement (`order_purchase_timestamp`). Any field reflecting post-purchase milestones, carrier operations, or customer feedback is strictly forbidden.

---

## 1. Authorized Predictor Feature Inventory

| Feature Name | Data Type | Source Grain | Description & Formula | Point-in-Time Availability Justification |
| :--- | :--- | :--- | :--- | :--- |
| `estimated_delivery_days` | Float (Days) | `fact_orders` | Promised delivery turnaround: $\frac{\text{estimated\_date} - \text{purchase\_time}}{86,400}$ | SLA window communicated to the customer at checkout. |
| `seller_dispatch_sla_days` | Float (Days) | `fact_order_items` | Contractual merchant dispatch deadline: $\frac{\text{shipping\_limit\_date} - \text{purchase\_time}}{86,400}$ | Platform fulfillment rule set upon order generation. |
| `distance_km` | Float (km) | `dim_geography` | Geodesic Haversine distance between customer zip centroid and primary seller zip centroid. | Customer and seller locations are fixed at checkout. |
| `promised_speed_km_per_day` | Float (km/day) | Derived | Promised velocity: $\frac{\text{distance\_km}}{\max(\text{estimated\_delivery\_days}, 1.0)}$ | Quantifies how aggressive the logistics SLA promise is relative to distance. |
| `total_items_count` | Integer | `fact_order_items` | Total count of product items in the order cart. | Known at checkout from basket composition. |
| `unique_sellers_count` | Integer | `fact_order_items` | Count of distinct merchants fulfilling the order. | Known at checkout from merchant routing. |
| `total_merchandise_value` | Float (BRL) | `fact_order_items` | Sum of item merchandise prices (`price`). | Cart total at checkout. |
| `total_freight_value` | Float (BRL) | `fact_order_items` | Sum of freight charges (`freight_value`). | Quoted freight price at checkout. |
| `freight_ratio` | Float | Derived | Ratio: $\frac{\text{total\_freight\_value}}{\max(\text{total\_merchandise\_value}, 1e-4)}$ | Economic freight burden of the parcel. |
| `freight_share` | Float | Derived | $\frac{\text{freight}}{\text{merchandise} + \text{freight}}$ | Normalized freight proportion of total basket gross value. |
| `total_weight_g` | Float (Grams) | `dim_products` | Total physical product weight across all items. | Catalog attribute known at checkout. |
| `total_volume_cm3` | Float ($\text{cm}^3$) | `dim_products` | Total parcel volume ($\text{length} \times \text{height} \times \text{width}$). | Catalog attribute known at checkout. |
| `max_dimension_cm` | Float (cm) | `dim_products` | Maximum individual dimension across order items. | Identifies oversized freight packages requiring LTL carriers. |
| `max_payment_installments` | Integer | `fact_payments` | Maximum installment slices chosen by buyer. | Chosen by buyer during payment selection at checkout. |
| `is_same_state` | Binary (0/1) | Derived | $1$ if customer state == primary seller state, else $0$. | Captures local intrastate vs interstate transit. |
| `is_same_region` | Binary (0/1) | Derived | $1$ if customer macro-region == seller macro-region. | Identifies inter-regional long-haul postal dispatch. |
| `is_interstate` | Binary (0/1) | Derived | $1$ if customer state $\ne$ primary seller state. | Interstate transport subject to interstate fiscal checks (ICMS). |
| `is_high_risk_destination` | Binary (0/1) | Derived | $1$ if destination is in historically delayed states (RJ, North, Northeast). | Fixed regional logistics infrastructure tiers. |
| `purchase_day_of_week` | Integer (0-6) | `fact_orders` | Day of week of purchase (0 = Monday, 6 = Sunday). | Extracted from `order_purchase_timestamp`. |
| `purchase_hour` | Integer (0-23) | `fact_orders` | Hour of purchase (0 to 23). | Extracted from `order_purchase_timestamp`. |
| `is_weekend` | Binary (0/1) | Derived | $1$ if purchase occurred on Saturday or Sunday. | Captures weekend postal dispatch buffer. |
| `customer_state` | String (Categorical) | `dim_customers` | Buyer Brazilian state (27 states). | Delivery address selected at checkout. |
| `seller_state` | String (Categorical) | `dim_sellers` | Primary seller Brazilian state. | Merchant origin location. |
| `customer_region` | String (Categorical) | Derived | Southeast, South, Northeast, Central-West, North. | Macro-regional grouping. |
| `seller_region` | String (Categorical) | Derived | Southeast, South, Northeast, Central-West, North. | Macro-regional grouping. |
| `category_grouped` | String (Categorical) | `dim_products` | Product category of highest-priced item (top 15 categories + 'other'). | Product line known at checkout. |
| `primary_payment_type` | String (Categorical) | `fact_payments` | Dominant payment method (credit card, boleto, voucher, debit card). | Payment method selected by buyer at checkout. |

---

## 2. Forbidden Data-Leakage Feature Register

The following fields are strictly **rejected** by automated governance tests:

| Forbidden Field Name | Originating Table | Why It Constitutes Data Leakage |
| :--- | :--- | :--- |
| `order_delivered_customer_date` | `fact_orders` | Actual customer delivery timestamp. Directly defines the target outcome. |
| `order_delivered_carrier_date` | `fact_orders` | Carrier handover milestone occurring days after order placement. |
| `delivery_lead_time_days` | `fact_orders` | Total actual transit duration calculated using customer delivery date. |
| `carrier_transit_days` | `fact_orders` | Carrier transit duration calculated using actual delivery date. |
| `seller_dispatch_days` | `fact_orders` | Actual seller dispatch timestamp occurring post-order. |
| `sla_variance_days` | `fact_orders` | Difference between actual delivery date and estimated delivery date. |
| `is_late` | `fact_orders` | Ground-truth supervised target label. |
| `is_eligible_for_sla` | `fact_orders` | Operational filtering flag dependent on delivery milestones. |
| `order_approved_at` | `fact_orders` | Payment clearance timestamp (e.g. 1–3 days lag for Boleto bancário). |
| `review_score` | `fact_reviews` | Customer satisfaction rating submitted post-delivery. |
| `review_comment_title` | `fact_reviews` | Customer review text submitted post-delivery. |
| `review_comment_message` | `fact_reviews` | Customer review text submitted post-delivery. |
| `review_creation_date` | `fact_reviews` | Timestamp of review invitation generated after delivery. |
| `review_answer_timestamp` | `fact_reviews` | Timestamp of review response submitted post-delivery. |
