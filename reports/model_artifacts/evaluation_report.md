# CommerceLens AI — Phase 4: Delivery-Risk ML Evaluation Report

**Model Architecture**: `logistic_regression` (L2-Regularized, Balanced Class Weighting)  
**Execution Date**: 2026-10-11 06:32:47 UTC  
**Dataset Scope**: Historically measurable delivered orders (96,470 orders, 8 missing delivery timestamps excluded).

---

## 1. Chronological Splitting Strategy

Evaluation uses strict chronological partitioning based on `order_purchase_timestamp` to emulate production forecasting and prevent look-ahead bias:

| Split Partition | Calendar Window | Observations ($N$) | Late Orders | Late Prevalence |
| :--- | :--- | :--- | :--- | :--- |
| **Training** | Inception to 2018-04-30 | 71,118 (73.72%) | 6,251 | **8.79%** |
| **Validation** | 2018-05-01 to 2018-06-30 | 12,845 (13.32%) | 639 | **4.97%** |
| **Holdout Test** | 2018-07-01 to 2018-08-29 | 12,507 (12.96%) | 936 | **7.48%** |

---

## 2. Model Performance vs Baseline

### Validation Set (Hyperparameter & Threshold Tuning)
- **Baseline Dummy PR-AUC**: `0.0497`
- **Model ROC-AUC**: `0.7902`
- **Model PR-AUC**: `0.1779` (**3.58x** baseline lift)
- **Validation-Tuned Decision Threshold**: `0.72` (Optimal $F_1 = 0.2577$)

### Untouched Chronological Holdout Test Set
| Metric | Majority Baseline | Model (Threshold 0.50) | Model (Selected Threshold 0.72) |
| :--- | :--- | :--- | :--- |
| **PR-AUC / Average Precision** | 0.0748 | **0.1157** | **0.1157** |
| **ROC-AUC** | 0.5000 | **0.6112** | **0.6112** |
| **Precision** | 0.0000 | 0.0943 | **0.1037** |
| **Recall** | 0.0000 | **0.7682** | 0.3205 |
| **$F_1$-Score** | 0.0000 | 0.1680 | **0.1567** |
| **Brier Score** | 0.0748 | **0.3360** | **0.3360** |

### Confusion Matrix on Test Set (Threshold = 0.72)
- **True Positives (Correct Late Alarms)**: 300
- **False Positives (False Alarms)**: 2,593
- **False Negatives (Missed Late Deliveries)**: 636
- **True Negatives (Correct On-Time Deliveries)**: 8,978

---

## 3. Top Predictive Features & Directional Impact

| Feature Name | Standardized Coef | Odds Ratio | Impact Direction |
| :--- | :--- | :--- | :--- |
| `seller_state_MA` | `0.84` | `2.3163` | Increases Late Risk |
| `seller_state_PE` | `-0.825` | `0.4382` | Decreases Late Risk |
| `customer_state_AL` | `0.7944` | `2.213` | Increases Late Risk |
| `promised_speed_km_per_day` | `0.7364` | `2.0884` | Increases Late Risk |
| `distance_km` | `-0.515` | `0.5975` | Decreases Late Risk |
| `seller_state_RS` | `-0.5003` | `0.6063` | Decreases Late Risk |
| `seller_state_BA` | `-0.4883` | `0.6136` | Decreases Late Risk |
| `estimated_delivery_days` | `-0.4867` | `0.6146` | Decreases Late Risk |
| `customer_state_RR` | `0.4777` | `1.6124` | Increases Late Risk |
| `customer_state_PR` | `-0.4736` | `0.6227` | Decreases Late Risk |

---

## 4. Subgroup Error Analysis by Customer Destination Region

| Destination Region | Observations | Actual Late Rate | Pred Late Rate | Precision | Recall | $F_1$ |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Southeast** | 8,864 | 8.68% | 16.01% | 0.1374 | 0.2536 | 0.1782 |
| **South** | 1,638 | 3.66% | 25.95% | 0.0588 | 0.4167 | 0.1031 |
| **Northeast** | 1,097 | 5.2% | 62.35% | 0.0687 | 0.8246 | 0.1269 |
| **Central-West** | 707 | 5.8% | 36.78% | 0.1 | 0.6341 | 0.1728 |
| **North** | 201 | 4.48% | 52.24% | 0.0667 | 0.7778 | 0.1228 |

---

## 5. Statistical Governance & Limitations

> [!IMPORTANT]
> STATISTICAL GOVERNANCE NOTICE: Feature contributions and odds ratios quantify observational statistical associations with late delivery under historical Correios/Olist operating conditions. They DO NOT establish causal mechanisms. For example, high freight ratios or extended SLA promises reflect inter-state transit difficulty and postal logistics pricing, not that charging more freight causes parcels to arrive late. Stakeholders must treat model outputs as risk indicators for operational monitoring, not guarantees or causal levers.

### Operational Realities & Known Limitations:
1. **Temporal Regime Shifts**: In May/June 2018, Brazil experienced a nationwide truck drivers' strike (*Greve dos caminhoneiros*), disrupting freight corridors and leading Correios to recalibrate estimated delivery SLAs in subsequent months. Evaluating on chronological holdouts reflects this true operational decay, explaining why test ROC-AUC (0.61) is lower than validation ROC-AUC (0.79).
2. **Prediction Scope**: The model is trained exclusively on orders with historically measurable delivery timestamps. Cancelled or unavailable orders are excluded from supervised evaluation because their counterfactual delivery outcome cannot be observed.
