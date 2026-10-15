# CommerceLens AI — Data Ingestion & Quality Audit Report

> **Audit Phase**: Phase 1 (Ingestion, Profiling & Quality Engineering)  
> **Governance Policy**: Grounded empirical findings only; zero fabricated values.  

---

## 1. Executive Summary & File Inventory

| Table Name | Source File | File Size (KB) | Row Count | Column Count | Parsed Datetime Columns |
|:---|:---|:---:|:---:|:---:|:---|
| `orders` | `olist_orders_dataset.csv` | 17241.1 | 99,441 | 8 | order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date |
| `order_items` | `olist_order_items_dataset.csv` | 15076.8 | 112,650 | 7 | shipping_limit_date |
| `order_payments` | `olist_order_payments_dataset.csv` | 5641.7 | 103,886 | 5 | None |
| `order_reviews` | `olist_order_reviews_dataset.csv` | 14113.0 | 99,224 | 7 | review_creation_date, review_answer_timestamp |
| `customers` | `olist_customers_dataset.csv` | 8822.2 | 99,441 | 5 | None |
| `sellers` | `olist_sellers_dataset.csv` | 170.6 | 3,095 | 4 | None |
| `products` | `olist_products_dataset.csv` | 2323.7 | 32,951 | 9 | None |
| `geolocation` | `olist_geolocation_dataset.csv` | 59837.8 | 1,000,163 | 5 | None |
| `category_translation` | `product_category_name_translation.csv` | 2.6 | 71 | 2 | None |

---

## 2. Duplicate Records Analysis

| Table Name | Total Rows | Complete Duplicates | Distinct Complete Rows | Duplicate % | Status |
|:---|:---:|:---:|:---:|:---:|:---|
| `orders` | 99,441 | 0 | 99,441 | 0.00% | Clean |
| `order_items` | 112,650 | 0 | 112,650 | 0.00% | Clean |
| `order_payments` | 103,886 | 0 | 103,886 | 0.00% | Clean |
| `order_reviews` | 99,224 | 0 | 99,224 | 0.00% | Clean |
| `customers` | 99,441 | 0 | 99,441 | 0.00% | Clean |
| `sellers` | 3,095 | 0 | 3,095 | 0.00% | Clean |
| `products` | 32,951 | 0 | 32,951 | 0.00% | Clean |
| `geolocation` | 1,000,163 | 261,831 | 738,332 | 26.18% | Contains Duplicates |
| `category_translation` | 71 | 0 | 71 | 0.00% | Clean |

> **Geolocation Granularity Clarification**:
> - Complete duplicate rows across all 5 columns: 261,831 rows (26.18%).
> - Distinct complete rows: 738,332 rows.
> - Candidate-key duplicate groups on `(zip_code_prefix, lat, lng)`: 131,707 distinct coordinates appearing > 1 time.
> - Excess candidate-key rows beyond 1 occurrence: 280,009 rows (`1,000,163 - 720,154`).
> - **Operational Resolution**: Aggregated to median latitude/longitude centroids grouped by 5-digit zip code prefix (19,010 records), avoiding 1:N fan-out joins.

---

## 3. Candidate Primary Key & Table Grain Validation

> **Metric Definitions**:
> - **`Distinct Keys`**: Count of unique candidate-key combinations ($N_{\text{unique}}$).
> - **`Duplicate Key Groups`**: Number of distinct candidate-key values appearing more than once ($\sum \mathbf{1}(\text{count}(k) > 1)$).
> - **`Excess Duplicate Rows`**: Redundant rows beyond one occurrence of each key ($\text{Total Rows} - N_{\text{unique}}$).

| Table Name | Candidate Key Columns | Total Rows | Distinct Keys | Duplicate Key Groups | Excess Duplicate Rows | Null Keys | Valid PK? | Notes |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `orders` | `order_id` | 99,441 | 99,441 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `order_items` | `order_id, order_item_id` | 112,650 | 112,650 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `order_payments` | `order_id, payment_sequential` | 103,886 | 103,886 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `order_reviews` | `review_id` | 99,224 | 98,410 | 789 | 814 | 0 | **NO** | Key failed validation: 789 duplicate key groups (814 excess rows), 0 null rows. |
| `customers` | `customer_id` | 99,441 | 99,441 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `sellers` | `seller_id` | 3,095 | 3,095 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `products` | `product_id` | 32,951 | 32,951 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `geolocation` | `geolocation_zip_code_prefix, geolocation_lat, geolocation_lng` | 1,000,163 | 720,154 | 131,707 | 280,009 | 0 | **NO** | Key failed validation: 131,707 duplicate key groups (280,009 excess rows), 0 null rows. |
| `category_translation` | `product_category_name` | 71 | 71 | 0 | 0 | 0 | **YES** | Unique and non-null grain verified. |
| `customers` | `customer_unique_id` | 99,441 | 96,096 | 2,997 | 3,345 | 0 | **NO** | Expected: customer_unique_id represents repeat buyers and is NOT a unique PK per order record. |
| `order_reviews` | `review_id, order_id` | 99,224 | 99,224 | 0 | 0 | 0 | **YES** | Compound candidate key for reviews. 100% unique across all review records. |

---

## 4. Referential Integrity & Foreign Key Analysis

| Relationship | Child Table.Column | Parent Table.Column | Child Total | Orphan Records | Referential Integrity % | Status |
|:---|:---|:---|:---:|:---:|:---:|:---|
| `order_items_to_orders` | `order_items.order_id` | `orders.order_id` | 112,650 | 0 | 100.00% | Clean (100%) |
| `order_items_to_products` | `order_items.product_id` | `products.product_id` | 112,650 | 0 | 100.00% | Clean (100%) |
| `order_items_to_sellers` | `order_items.seller_id` | `sellers.seller_id` | 112,650 | 0 | 100.00% | Clean (100%) |
| `order_payments_to_orders` | `order_payments.order_id` | `orders.order_id` | 103,886 | 0 | 100.00% | Clean (100%) |
| `order_reviews_to_orders` | `order_reviews.order_id` | `orders.order_id` | 99,224 | 0 | 100.00% | Clean (100%) |
| `orders_to_customers` | `orders.customer_id` | `customers.customer_id` | 99,441 | 0 | 100.00% | Clean (100%) |
| `products_to_category_translation` | `products.product_category_name` | `category_translation.product_category_name` | 32,951 | 13 | 98.11% | Unmatched: 13 |

---

## 5. Missing Values Summary (Top Missing Columns)

| Table Name | Column Name | Missing Count | Total Rows | Missing % |
|:---|:---|:---:|:---:|:---:|
| `order_reviews` | `review_comment_title` | 87,656 | 99,224 | 88.34% |
| `order_reviews` | `review_comment_message` | 58,247 | 99,224 | 58.70% |
| `orders` | `order_delivered_customer_date` | 2,965 | 99,441 | 2.98% |
| `products` | `product_category_name` | 610 | 32,951 | 1.85% |
| `products` | `product_name_lenght` | 610 | 32,951 | 1.85% |
| `products` | `product_description_lenght` | 610 | 32,951 | 1.85% |
| `products` | `product_photos_qty` | 610 | 32,951 | 1.85% |
| `orders` | `order_delivered_carrier_date` | 1,783 | 99,441 | 1.79% |
| `orders` | `order_approved_at` | 160 | 99,441 | 0.16% |
| `products` | `product_weight_g` | 2 | 32,951 | 0.01% |
| `products` | `product_length_cm` | 2 | 32,951 | 0.01% |
| `products` | `product_height_cm` | 2 | 32,951 | 0.01% |
| `products` | `product_width_cm` | 2 | 32,951 | 0.01% |

---

## 6. Significant Quality Findings & Domain Anomalies

### [CANDIDATE_INVESTIGATION] Delivered Status with Missing Delivery Timestamp (`ORD_STAT_01`)
- **Table / Column**: `orders` / `order_delivered_customer_date`
- **Evidence**: 8 orders marked as 'delivered' have a NULL order_delivered_customer_date. Accounts for 8 of 2,965 total missing delivery timestamps.
- **Recommended Action**: Do not compute lead times on these orders; investigate whether delivery confirmation was omitted.
- **Safe to Automatically Clean**: No (requires investigation or filter rule)

### [EXPECTED_CHARACTERISTIC] Non-Delivered Orders with Null Delivery Dates (`ORD_STAT_02`)
- **Table / Column**: `orders` / `order_delivered_customer_date`
- **Evidence**: 2,957 orders across all non-delivered statuses naturally have NULL delivery dates (shipped=1,107, canceled=619, unavailable=609, invoiced=314, processing=301, created=5, approved=2). Fully reconciles all missing values: 8 delivered + 2,957 non-delivered = 2,965 total missing.
- **Recommended Action**: Filter order_status = 'delivered' before running logistics lead-time analyses.
- **Safe to Automatically Clean**: Yes

### [CANDIDATE_INVESTIGATION] Zero Value Payment Slices (`PAY_VAL_02`)
- **Table / Column**: `order_payments` / `payment_value`
- **Evidence**: 9 payments have payment_value = 0.00 (likely 100% voucher applied).
- **Recommended Action**: Retain vouchers while auditing full voucher discount reconciliation.
- **Safe to Automatically Clean**: No (requires investigation or filter rule)

### [CANDIDATE_INVESTIGATION] Coordinates Outside Brazilian Geographic Bounding Box (`GEO_BOUND_01`)
- **Table / Column**: `geolocation` / `geolocation_lat`
- **Evidence**: 40 coordinate records fall outside continental Brazil coordinates.
- **Recommended Action**: Filter coordinates before spatial distance calculations or compute median centroid per zip prefix.
- **Safe to Automatically Clean**: No (requires investigation or filter rule)

### [CONFIRMED_ISSUE] Product Category Translation Mapping Gaps (`PROD_CAT_01`)
- **Table / Column**: `products` / `product_category_name`
- **Evidence**: 610 products have NULL product_category_name. 13 products have non-null categories lacking an English translation across 2 distinct categories: 'portateis_cozinha_e_preparadores_de_alimentos' (10 products), 'pc_gamer' (3 products).
- **Recommended Action**: Do not invent placeholder categories or discard records. In Phase 2 DDL/reporting, leave English category as NULL or map 'pc_gamer' -> 'pc_gamer' and 'portateis_cozinha_e_preparadores_de_alimentos' -> 'portable_kitchen_food_preparers'.
- **Safe to Automatically Clean**: No (requires investigation or filter rule)

---

## 7. Recommendations for Phase 2 (Relational Modeling & Star Schema)
1. **Star Schema Primary Keys**: Use verified unique grains as surrogate keys.
2. **Fan-Out Prevention**: Strict CTE pre-aggregation for multi-item and multi-payment orders before joining.
3. **Geolocation Pre-aggregation**: Join orders and sellers to zip code centroid table rather than the raw 1-to-many coordinate records.
4. **Status Filtering**: Create separate reporting views for delivered vs canceled orders.
