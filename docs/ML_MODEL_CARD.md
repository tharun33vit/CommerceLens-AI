# CommerceLens AI — Model Card: Delivery-Risk Prediction

> **Model Overview**: An interview-defensible, regularized classification model designed to predict late-delivery risk for Brazilian e-commerce orders at the moment of checkout, using strictly point-in-time predictors.

---

## 1. Model Details
- **Model Name**: CommerceLens AI Delivery-Risk Classifier
- **Model Architecture**: L2-Regularized Logistic Regression (`scikit-learn.linear_model.LogisticRegression`) with Standardized Numerical Features and One-Hot Encoded Categoricals (`ColumnTransformer`).
- **Hyperparameters**: $C = 0.1$, `class_weight='balanced'`, `penalty='l2'`, `solver='lbfgs'`, `random_state=42`.
- **Primary Operational Threshold**: `0.72` (selected on chronological validation data).
- **Default Baseline Threshold**: `0.50`.
- **Training Date**: October 2026 (evaluated on historical 2016–2018 Olist e-commerce snapshot).
- **License**: MIT.

---

## 2. Intended Use & Prediction Scope
- **Primary Use Case**: Proactive fulfillment monitoring at checkout. Flagging high-risk orders to logistics operations teams for priority fulfillment, carrier routing review, or automated customer delivery window expectation management.
- **Prediction Scope**: The model is trained and evaluated on **historically measurable delivered orders** ($N = 96,470$).
  - **Exclusion 1**: Exactly 8 delivered orders missing customer-delivery timestamps are excluded.
  - **Exclusion 2**: Cancelled, unavailable, or currently in-transit orders are excluded from supervised evaluation because their ultimate delivery outcome cannot be observed counterfactually.
- **Out-of-Scope**: Do not use this model as an automated contract guarantee or to penalize sellers without human review.
- **Governance Disclosure**: The 27-feature model artifact (`model_pipeline.joblib`) is retained in the application for software interface compatibility and historical baseline comparison. It is **not approved for operational checkout-time scoring** because its predictor `seller_dispatch_sla_days` depends on post-purchase order approval timing. The primary checkout-safe research candidate is the **34-feature unweighted Logistic Regression model ($C=0.1$)** (validation ROC-AUC 0.7918, PR-AUC 0.1821 at threshold 0.18), documented in [reports/model_artifacts/ml_improvement_phase2_report.md](../reports/model_artifacts/ml_improvement_phase2_report.md).

---

## 3. Training & Evaluation Population
- **Total Population**: 96,470 delivered orders with valid delivery milestones.
- **Late Deliveries (Class 1)**: 7,826 orders (8.11%).
- **On-Time Deliveries (Class 0)**: 88,644 orders (91.89%).
- **Chronological Partitions**:
  - **Training Split**: Inception (2016-09-15) to 2018-04-30 ($N = 71,118$, 73.72%, Late Rate = 8.79%).
  - **Validation Split**: 2018-05-01 to 2018-06-30 ($N = 12,845$, 13.32%, Late Rate = 4.97%).
  - **Holdout Test Split**: 2018-07-01 to 2018-08-29 ($N = 12,507$, 12.96%, Late Rate = 7.48%).

---

## 4. Quantitative Performance Metrics

### Validation Set (Threshold Tuning Period)
- **Majority-Class Baseline PR-AUC**: `0.0497`
- **Model PR-AUC**: `0.1779` (**3.58x lift over baseline**)
- **Model ROC-AUC**: `0.7902`
- **Optimal Threshold ($F_1$-maximized)**: `0.72` (Precision = `0.2293`, Recall = `0.2942`, $F_1 = 0.2577$)

### Untouched Chronological Holdout Test Set (2018-07-01 to 2018-08-29)
| Evaluation Metric | Majority-Class Baseline | Model (Default Thresh = 0.50) | Model (Validation Selected = 0.72) |
| :--- | :--- | :--- | :--- |
| **PR-AUC / Average Precision** | 0.0748 | **0.1157** (1.55x lift) | **0.1157** (1.55x lift) |
| **ROC-AUC** | 0.5000 | **0.6112** | **0.6112** |
| **Precision (Late Class)** | 0.0000 | 0.0943 | **0.1037** |
| **Recall (Late Class)** | 0.0000 | **0.7682** (719/936 caught) | 0.3205 (300/936 caught) |
| **$F_1$-Score** | 0.0000 | **0.1680** | 0.1567 |
| **Brier Score** | 0.0692 | 0.1774 | **0.1774** |

### Test Confusion Matrix (Threshold = 0.72)
$$\begin{pmatrix} \text{TN: } 8,978 & \text{FP: } 2,593 \\ \text{FN: } 636 & \text{TP: } 300 \end{pmatrix}$$

---

## 5. Top Predictive Drivers & Directional Odds Ratios
Extracted from standardized Logistic Regression coefficients:

1. **Destination State `RR` (Roraima)** ($\beta = +1.665$, Odds Ratio = $5.29$): Severe logistics distance in extreme North Amazon corridor.
2. **Promised Speed `promised_speed_km_per_day`** ($\beta = +0.807$, Odds Ratio = $2.24$): Aggressive delivery SLA promises requiring unsustainable daily transit distance.
3. **Destination State `RJ` (Rio de Janeiro)** ($\beta = +0.648$, Odds Ratio = $1.91$): Known metropolitan postal sorting hub congestion in Correios.
4. **Seller Region `North`** ($\beta = +0.637$, Odds Ratio = $1.89$): Originating fulfillment from northern logistics hubs.
5. **Geodesic Distance `distance_km`** ($\beta = -0.610$, Odds Ratio = $0.54$): When conditioned on promised speed and state, long-distance routes often carry large SLA buffers that mitigate delay risk.
6. **Destination State `PR` (Paraná)** ($\beta = -0.566$, Odds Ratio = $0.57$): High-density southern logistics infrastructure reduces delay risk.

---

## 6. Scientific Governance & Causality Disclaimer
> [!IMPORTANT]
> **Non-Causality Principle**: Standardized coefficients and odds ratios quantify **observational correlations** under historical Correios/Olist postal logistics dynamics. They do **not** represent causal levers. Increasing freight prices or altering customer states in the feature vector will not causally change transit physics.

---

## 7. Known Limitations & Macroeconomic Regime Shifts
1. **Temporal Degradation**: Performance decays between validation (ROC-AUC 0.79) and test (ROC-AUC 0.61) due to the nationwide truck drivers' strike (*Greve dos caminhoneiros*) in late May 2018. Following the strike, Correios adjusted transit SLAs and clearing times, altering the historical distribution.
2. **Observational Selection**: The model predicts outcomes for orders that were fulfilled. It cannot predict counterfactual delivery risk for orders cancelled prior to fulfillment.
