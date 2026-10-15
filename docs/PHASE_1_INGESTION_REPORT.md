# CommerceLens AI — Phase 1: Ingestion, Profiling and Quality Audit Technical Report

> **Phase**: Phase 1 — Data Ingestion, Profiling & Quality Audit (Audit Reconciliation & Validation Hardening)  
> **Status**: Successfully executed against the complete real Olist Brazilian E-Commerce dataset. All 19 unit & smoke tests passing.  
> **Governance Rule**: Grounded empirical findings only; zero fabricated values.

---

## 1. Executive Summary & Verified Dataset Inventory

All 9 expected raw Olist dataset files were discovered in `data/raw/` and ingested without modifying source files:

| Table Name | Source Filename | File Size | Verified Row Count | Column Count | Inferred Key Grain |
|:---|:---|:---:|:---:|:---:|:---|
| `orders` | `olist_orders_dataset.csv` | 17.65 MB | **99,441** | 8 | `order_id` (100% unique) |
| `order_items` | `olist_order_items_dataset.csv` | 15.44 MB | **112,650** | 7 | `(order_id, order_item_id)` (100% unique) |
| `order_payments` | `olist_order_payments_dataset.csv` | 5.78 MB | **103,886** | 5 | `(order_id, payment_sequential)` (100% unique) |
| `order_reviews` | `olist_order_reviews_dataset.csv` | 14.45 MB | **99,224** | 7 | Compound `(review_id, order_id)` (100% unique) |
| `customers` | `olist_customers_dataset.csv` | 9.03 MB | **99,441** | 5 | `customer_id` (100% unique per transaction) |
| `sellers` | `olist_sellers_dataset.csv` | 174.7 KB | **3,095** | 4 | `seller_id` (100% unique) |
| `products` | `olist_products_dataset.csv` | 2.38 MB | **32,951** | 9 | `product_id` (100% unique) |
| `geolocation` | `olist_geolocation_dataset.csv` | 61.27 MB | **1,000,163** | 5 | Multi-coordinate per zip prefix (aggregated to 19,010 centroids) |
| `category_translation` | `product_category_name_translation.csv` | 2.61 KB | **71** | 2 | `product_category_name` (100% unique) |

---

## 2. Audit Reconciliation Findings & Root Causes

### 2.1 Reconciled Delivery Timestamp Null Counts
- **Total Missing `order_delivered_customer_date`**: Exactly **2,965 orders**.
- **Root Cause of Initial 7-Record Discrepancy**:
  The initial audit script hardcoded a static list of non-delivered statuses (`canceled`, `unavailable`, `invoiced`, `shipped`, `processing`), which summed to 2,950. It omitted two valid Olist statuses present in the dataset:
  - `created`: **5 orders**
  - `approved`: **2 orders**
  $2,950 + 5 + 2 = 2,957$ non-delivered orders.
- **Complete Reconciled Status Breakdown**:
  | Order Status | Count with Missing Delivery Timestamp | Classification |
  |:---|:---:|:---|
  | `shipped` | 1,107 | Expected (in transit) |
  | `canceled` | 619 | Expected (never fulfilled) |
  | `unavailable` | 609 | Expected (out of stock/inventory failure) |
  | `invoiced` | 314 | Expected (awaiting dispatch) |
  | `processing` | 301 | Expected (packing/processing) |
  | `created` | 5 | Expected (checkout initiated) |
  | `approved` | 2 | Expected (payment approved, not dispatched) |
  | **Subtotal Non-Delivered** | **2,957** | **Expected Operational Characteristic** |
  | `delivered` | **8** | **Candidate Investigation (Missing Milestone)** |
  | **Total Missing Delivery Dates** | **2,965** | **100% Mathematically Reconciled** |

---

### 2.2 Clarified Duplicate-Key Metrics & Geolocation Granularity
To eliminate ambiguity between duplicate key occurrences and redundant rows, two distinct mathematical metrics are implemented:
1. **`duplicate_key_groups`**: Number of distinct candidate-key values appearing $> 1$ time ($\sum \mathbf{1}(\text{count}(k) > 1)$).
2. **`excess_duplicate_rows`**: Redundant rows beyond 1 occurrence per key ($\text{Total Rows} - N_{\text{unique}}$).

#### Verified Empirical Key Metrics:
| Table Name | Candidate Key | Total Rows | Distinct Keys | Duplicate Key Groups | Excess Duplicate Rows | Valid PK? | Status / Notes |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `orders` | `order_id` | 99,441 | 99,441 | 0 | 0 | **YES** | Strict 1:1 grain |
| `order_items` | `(order_id, order_item_id)` | 112,650 | 112,650 | 0 | 0 | **YES** | Multi-item grain |
| `order_payments` | `(order_id, payment_sequential)` | 103,886 | 103,886 | 0 | 0 | **YES** | Split payment grain |
| `order_reviews` | `review_id` | 99,224 | 98,410 | 789 | 814 | **NO** | 789 IDs appear on multiple orders |
| `order_reviews` | `(review_id, order_id)` | 99,224 | 99,224 | **0** | **0** | **YES** | **Strict compound PK validated** |
| `customers` | `customer_id` | 99,441 | 99,441 | 0 | 0 | **YES** | Order-level token |
| `customers` | `customer_unique_id` | 99,441 | 96,096 | 2,997 | 3,345 | **NO** | Tracks 2,997 repeat buyers |
| `sellers` | `seller_id` | 3,095 | 3,095 | 0 | 0 | **YES** | Merchant grain |
| `products` | `product_id` | 32,951 | 32,951 | 0 | 0 | **YES** | SKU catalog grain |
| `geolocation` | `(zip_prefix, lat, lng)` | 1,000,163 | 720,154 | 131,707 | 280,009 | **NO** | High spatial multiplicity |
| `category_translation` | `product_category_name` | 71 | 71 | 0 | 0 | **YES** | Translation lookup grain |

#### Geolocation Deep Dive:
- Total rows: **1,000,163**
- Complete duplicate rows (identical across all 5 columns): **261,831** (26.18%)
- Distinct complete rows: **738,332**
- Candidate key `(zip_code_prefix, lat, lng)` distinct values: **720,154**
- Candidate-key duplicate groups: **131,707**
- Excess candidate-key rows beyond 1 occurrence: **280,009** ($1,000,163 - 720,154$)
- **Resolution**: Aggregated to **19,010 median centroids** per 5-digit zip code prefix (`cleaned_geolocation_centroids`), filtering 40 non-Brazil outliers and strictly preventing 1:N fan-out joins.

---

### 2.3 Product Category Translation Gaps
Investigation of `olist_products_dataset.csv` against `product_category_name_translation.csv` revealed three distinct conditions:
1. **Products with NULL `product_category_name`**: Exactly **610 products** (1.85% of catalog).
2. **Products whose non-null category lacks an English translation**: Exactly **13 products**.
3. **Distinct category values lacking translation**: Exactly **2 categories**:
   - `'portateis_cozinha_e_preparadores_de_alimentos'`: **10 products**
   - `'pc_gamer'`: **3 products**
- **Correction Applied in Cleaning Pipeline**:
  Removed artificial `.fillna("unclassified")`. In accordance with zero-fabrication principles, unmapped categories retain `NaN` in `product_category_name_english`. In Phase 2 DDL/reporting, verified mappings (`pc_gamer` $\to$ `pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos` $\to$ `portable_kitchen_food_preparers`) will be applied via documented DDL updates.

---

## 3. Cleaning Pipeline Verification & Row-Count Reconciliation

| Entity | Raw Rows | Processed Rows | Row Difference | Explanation |
|:---|:---:|:---:|:---:|:---|
| `orders` | 99,441 | 99,441 | **0** | All records preserved; SLA flags added |
| `order_items` | 112,650 | 112,650 | **0** | All records preserved; gross value computed |
| `order_payments` | 103,886 | 103,886 | **0** | All records preserved |
| `order_reviews` | 99,224 | 99,224 | **0** | All records preserved; compound PK verified |
| `customers` | 99,441 | 99,441 | **0** | All records preserved; CEP zero-padded (`zfill(5)`) |
| `sellers` | 3,095 | 3,095 | **0** | All records preserved; CEP zero-padded |
| `products` | 32,951 | 32,951 | **0** | All records preserved; English translation mapped |
| `category_translation` | 71 | 71 | **0** | All records preserved |
| `geolocation` | 1,000,163 | 19,010 | **-981,153** | 40 non-Brazil outliers filtered; 1:N coordinate points aggregated to median centroid per 5-digit zip code prefix |

- **Raw Source Preservation**: SHA-256 hashes of all 9 raw CSV files are unchanged.
- **Rerun Idempotency**: Verified by running `python scripts/run_data_audit.py` repeatedly without state corruption.

---

## 4. Test Suite Execution Results

Command executed:
```powershell
python -m pytest tests/
```

Output:
```text
============================== test session starts ==============================
rootdir: C:\Users\Admin\Desktop\CommerceLens-AI
configfile: pyproject.toml
testpaths: tests
collected 19 items

tests/test_data_pipeline.py::test_missing_required_files PASSED            [  5%]
tests/test_data_pipeline.py::test_successful_csv_discovery_and_loading PASSED [ 10%]
tests/test_data_pipeline.py::test_missing_value_profiling PASSED           [ 15%]
tests/test_data_pipeline.py::test_duplicate_detection PASSED               [ 21%]
tests/test_data_pipeline.py::test_candidate_key_validation PASSED         [ 26%]
tests/test_data_pipeline.py::test_foreign_key_integrity_checks PASSED      [ 31%]
tests/test_data_pipeline.py::test_invalid_date_handling PASSED             [ 36%]
tests/test_data_pipeline.py::test_report_generation PASSED                 [ 42%]
tests/test_data_pipeline.py::test_preservation_of_raw_files PASSED         [ 47%]
tests/test_data_pipeline.py::test_full_pipeline_halt_on_missing_files PASSED [ 52%]
tests/test_data_pipeline.py::test_delivery_date_reconciliation PASSED      [ 57%]
tests/test_data_pipeline.py::test_duplicate_metric_definitions PASSED      [ 63%]
tests/test_data_pipeline.py::test_category_mapping_gaps_distinction PASSED [ 68%]
tests/test_smoke.py::test_python_version_supported PASSED                  [ 73%]
tests/test_smoke.py::test_package_import_and_metadata PASSED               [ 78%]
tests/test_smoke.py::test_submodules_exist PASSED                          [ 84%]
tests/test_smoke.py::test_directory_structure_exists PASSED               [ 89%]
tests/test_smoke.py::test_core_configuration_files_exist PASSED           [ 94%]
tests/test_smoke.py::test_docs_exist PASSED                                [100%]

============================== 19 passed in 2.35s ==============================
```
**19 passed, 0 failed, 0 warnings.**
