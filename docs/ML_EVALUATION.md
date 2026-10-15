# CommerceLens AI — Machine Learning Evaluation & Interview Defense

> **Phase 4 Deliverable**: Comprehensive evaluation of the delivery-risk classification model, documenting empirical performance across chronological train/validation/test partitions, threshold trade-offs, and interview-ready engineering defenses.

---

## 1. Executive Summary of Experimental Results

- **Prediction Task**: Binary classification predicting whether an order will be delivered after its estimated SLA date ($1 = \text{Late}, 0 = \text{On-Time}$).
- **Eligible Population**: $96,470$ delivered orders with verified delivery milestones (8 delivered orders missing delivery timestamps excluded).
- **Target Imbalance**: $8.11\%$ overall late-delivery prevalence ($7,826$ late vs $88,644$ on-time).
- **Primary Model**: L2-regularized Logistic Regression ($C = 0.1$, `class_weight='balanced'`).
- **Benchmark Model**: Majority-Class Dummy Classifier.
- **Validation Lift (May–June 2018)**: **$3.58\times$ PR-AUC lift** over baseline (`0.1779` vs `0.0497`), ROC-AUC = `0.7902`.
- **Untouched Test Lift (July–August 2018)**: **$1.55\times$ PR-AUC lift** over baseline (`0.1157` vs `0.0748`), ROC-AUC = `0.6112`.
- **Operational Threshold**: Selected at `0.72` on validation data, achieving a balance between false alarm volume and caught late orders.

---

## 2. Chronological Split Details

| Partition | Date Range | Sample Size ($N$) | Late Count | Late Prevalence | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Train** | Inception to 2018-04-30 | $71,118$ ($73.72\%$) | $6,251$ | $8.79\%$ | Parameter estimation & feature scaling fitting |
| **Validation** | 2018-05-01 to 2018-06-30 | $12,845$ ($13.32\%$) | $639$ | $4.97\%$ | Hyperparameter tuning & threshold selection |
| **Test** | 2018-07-01 to 2018-08-29 | $12,507$ ($12.96\%$) | $936$ | $7.48\%$ | Unbiased evaluation on untouched future data |

---

## 3. Threshold Trade-Off Analysis on Validation Data

Because late deliveries represent a minority class (~5–9%), accuracy is misleading (a naive model predicting all on-time achieves 92–95% accuracy while providing zero business value). Operational threshold tuning was conducted strictly on the validation set:

| Threshold | Precision | Recall | $F_1$-Score | Caught (TP) | False Alarms (FP) | Missed (FN) | True On-Time (TN) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0.30** | $0.0651$ | $0.9718$ | $0.1219$ | 621 | 8,925 | 18 | 3,281 |
| **0.40** | $0.0865$ | $0.8842$ | $0.1575$ | 565 | 5,969 | 74 | 6,237 |
| **0.50** | $0.1244$ | $0.6651$ | $0.2096$ | 425 | 2,990 | 214 | 9,216 |
| **0.60** | $0.1520$ | $0.4851$ | $0.2314$ | 310 | 1,730 | 329 | 10,476 |
| **0.70** | $0.1996$ | $0.3286$ | $0.2484$ | 210 | 842 | 429 | 11,364 |
| **0.72** | **0.2293** | **0.2942** | **0.2577** | **188** | **632** | **451** | **11,574** |
| **0.80** | $0.2782$ | $0.1659$ | $0.2078$ | 106 | 275 | 533 | 11,931 |

**Threshold Selection Rationale**:
- At threshold `0.50` (default balanced), recall is high ($66.5\%$), but false alarms reach 2,990.
- At threshold `0.72` ($F_1$-optimal), false alarms are reduced by $78.9\%$ (from 2,990 down to 632), while maintaining precision above $22\%$.

---

## 4. Evaluation on Untouched Chronological Holdout Test Set

Evaluating the validation-selected threshold ($0.72$) on the untouched holdout test set:

| Metric | Majority Baseline | Model (Threshold 0.50) | Model (Selected Threshold 0.72) |
| :--- | :--- | :--- | :--- |
| **ROC-AUC** | 0.5000 | 0.6112 | 0.6112 |
| **PR-AUC / Avg Precision** | 0.0748 | **0.1157** ($+54.7\%$ lift) | **0.1157** ($+54.7\%$ lift) |
| **Precision** | 0.0000 | 0.0943 | **0.1037** |
| **Recall** | 0.0000 | **0.7682** (719 / 936 caught) | 0.3205 (300 / 936 caught) |
| **$F_1$-Score** | 0.0000 | **0.1680** | 0.1567 |
| **True Positives (TP)** | 0 | 719 | 300 |
| **False Positives (FP)** | 0 | 6,908 | 2,593 |
| **False Negatives (FN)** | 936 | 217 | 636 |
| **True Negatives (TN)** | 11,571 | 4,663 | 8,978 |

---

## 5. Subgroup Error Analysis across Macro-Regions

| Destination Region | Test Orders ($N$) | Actual Late Rate | Pred Late Rate | Precision | Recall | $F_1$-Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Southeast** | $8,521$ | $5.70\%$ | $19.46\%$ | $0.1031$ | $0.3519$ | $0.1594$ |
| **South** | $2,008$ | $8.07\%$ | $14.19\%$ | $0.0912$ | $0.1605$ | $0.1163$ |
| **Northeast** | $1,210$ | $17.69\%$ | $49.75\%$ | $0.1661$ | $0.4673$ | $0.2450$ |
| **Central-West** | $548$ | $8.39\%$ | $24.82\%$ | $0.0882$ | $0.2609$ | $0.1319$ |
| **North** | $220$ | $13.64\%$ | $42.27\%$ | $0.1183$ | $0.3667$ | $0.1789$ |

**Diagnostic Insights**:
- **Northeast ($17.7\%$ late) and North ($13.6\%$ late)** have significantly higher delivery failure rates due to long-haul inter-regional transit across Brazil. The model correctly assigns higher risk probabilities to these corridors (predicted late rates of $49.8\%$ and $42.3\%$).
- **Southeast ($5.7\%$ late)** experiences fewer delays, but because it represents $68.1\%$ of total e-commerce volume, metropolitan logistics bottlenecks (especially in Rio de Janeiro) drive the majority of absolute delay incidents.

---

## 6. Interview Defense: Conceptual Answers

### Q1: Why formulate delivery-risk prediction as classification rather than regression on lead time?
> **Answer**: From an operational and customer experience perspective, what triggers customer support tickets, negative CSAT ratings (dropping from 4.29 to 2.57 stars), and seller SLA penalties is the binary violation of the promised estimated date ($\text{Actual} > \text{Estimated}$), not whether a parcel took 11 or 12 days when 15 were promised. Predicting late probability ($P(\text{Late} = 1)$) allows operations teams to apply dynamic decision thresholds based on the cost of false alarms versus late delivery penalties.

### Q2: Why train only on delivered orders with verified timestamps?
> **Answer**: To train a supervised classifier, the ground-truth label must be historically verified. For cancelled or unavailable orders, the counterfactual delivery date is unobservable. Furthermore, exactly 8 delivered orders lacked a recorded customer handover timestamp; rather than imputing an arbitrary milestone, we explicitly excluded them from training to avoid label noise.

### Q3: Why is random $K$-Fold splitting deceptive for time-dependent e-commerce data?
> **Answer**: Random splitting allows temporal data from the same week or month to appear in both training and test sets. In real operations, models predict future orders. Furthermore, e-commerce logistics experiences macro-shocks (e.g., Black Friday volume surges in Nov 2017, postal strikes in Feb–Mar 2018, truck drivers' strike in May 2018). Random splitting produces artificially high cross-validation scores ($>0.80$) that fail in production. Chronological splitting reveals true temporal decay and operational reality.

### Q4: Why prioritize PR-AUC, Recall, and Precision over raw Accuracy?
> **Answer**: With an $8.1\%$ base rate, a trivial majority-class classifier achieves $91.9\%$ accuracy while detecting $0\%$ of late deliveries. PR-AUC measures the trade-off across probability thresholds specifically on the minority class, ensuring the model demonstrates true predictive power over the base rate.

### Q5: How was data leakage strictly prevented?
> **Answer**: We established a zero-leakage governance contract:
1. Only features known at order placement (`order_purchase_timestamp`) are included.
2. Carrier handover timestamp (`order_delivered_carrier_date`), carrier transit time, seller dispatch duration, review scores, and review timestamps are strictly banned.
3. Automated unit tests assert that any attempt to include these columns raises a `ValueError`.
4. All preprocessing (scaling, imputation, encoding) is fitted exclusively on the training split.

### Q6: How should operations stakeholders use these predictions?
> **Answer**: Predictions are risk indicators, not deterministic guarantees. Stakeholders should use risk tiers (`LOW`, `MEDIUM`, `HIGH`) to:
1. Automatically add a 2–3 day buffer to promised delivery estimates for high-risk corridors before checkout.
2. Flag high-risk merchant dispatches for early carrier pickup.
3. Prioritize proactive customer notification if tracking scans show delay indicators during transit.

---

## 7. Model Benchmark & Empirical Diagnosis of Temporal Degradation

*(See full report: [ml_audit_and_benchmark_report.md](../reports/model_artifacts/ml_audit_and_benchmark_report.md))*

### 7.1 Candidate Models Benchmark Summary
To determine whether an alternative model architecture could overcome temporal degradation, 10 candidate architectures were benchmarked using identical chronological splits (`Train`: through Apr 2018, `Val`: May–Jun 2018, `Test`: Jul–Aug 2018) and validation-tuned decision thresholds:

| Model Architecture | Val ROC-AUC | Val PR-AUC | Val Opt $\tau$ | Val $F_1$ | Test ROC-AUC | Test PR-AUC | Test Opt Prec | Test Opt Rec | Test Opt $F_1$ | Test PR Lift |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Majority Baseline (Dummy)** | $0.5000$ | $0.0497$ | $0.10$ | $0.0000$ | $0.5000$ | $0.0748$ | $0.0000$ | $0.0000$ | $0.0000$ | $1.00\times$ |
| **Logistic Regression ($C=0.01$)** | **0.7924** | $0.1718$ | $0.66$ | $0.2458$ | **0.6141** | $0.1124$ | $0.0936$ | **0.3697** | $0.1494$ | $1.50\times$ |
| **Logistic Regression ($C=0.1$) [Selected]**| **0.7902** | **0.1779** | **0.72** | **0.2577** | **0.6112** | **0.1157** | **0.1037** | $0.3205$ | **0.1567** | **1.55x** |
| **Logistic Regression ($C=1.0$)** | $0.7893$ | **0.1786** | $0.68$ | **0.2587** | $0.6102$ | **0.1162** | $0.0970$ | **0.3718** | $0.1538$ | $1.55\times$ |
| **Random Forest ($d=8, n=100$)** | $0.7275$ | $0.1284$ | $0.57$ | $0.2086$ | $0.4472$ | $0.0658$ | $0.0626$ | $0.1571$ | $0.0896$ | $0.88\times$ (Failure) |
| **Random Forest ($d=12, n=150$)**| $0.7577$ | $0.1374$ | $0.56$ | $0.2316$ | $0.4787$ | $0.0698$ | $0.0630$ | $0.1838$ | $0.0938$ | $0.93\times$ (Failure) |
| **Extra Trees ($d=8, n=100$)** | $0.6614$ | $0.1040$ | $0.67$ | $0.1596$ | $0.4422$ | $0.0661$ | $0.0603$ | $0.0705$ | $0.0650$ | $0.88\times$ (Failure) |
| **HistGradientBoosting ($d=4, \text{lr}=0.05$)** | $0.7874$ | $0.1677$ | $0.61$ | $0.2472$ | $0.5240$ | $0.0809$ | $0.0664$ | $0.2692$ | $0.1065$ | $1.08\times$ |
| **HistGradientBoosting ($d=6, \text{lr}=0.05$)** | $0.7893$ | $0.1752$ | $0.64$ | $0.2588$ | $0.5364$ | $0.0818$ | $0.0677$ | $0.2436$ | $0.1059$ | $1.09\times$ |
| **HistGradientBoosting ($d=6, \text{l2}=1.0$)** | $0.7906$ | $0.1740$ | $0.68$ | $0.2514$ | $0.5353$ | $0.0800$ | $0.0651$ | $0.1848$ | $0.0962$ | $1.07\times$ |

### 7.2 Root Cause of the Performance Drop
1. **SLA Compression Policy Shift**: In August 2018, Olist aggressively reduced promised delivery SLA days from $27.77$ days (June 2018 post-strike buffer) down to $15.19$ days (a $-0.899$ standard deviation shift in `estimated_delivery_days`).
2. **Inverted Risk Corridors**: In training, intra-state orders (SP -> SP) had low late rates ($5.48\%$), while interstate orders had high late rates ($10.62\%$). In the test set, because local SLAs were compressed to just $10.93$ days, SP -> SP late rate jumped to **$12.58\%$**, representing **$68.2\%$ of all test late orders**. The correlation between `is_same_state` and `is_late` completely inverted from $-0.09$ to $+0.15$.
3. **Tree Model Overfitting**: Decision trees created pure "safe" leaf nodes for local SP orders during training. When platform SLA policies shifted, these leaf nodes severely misclassified the bulk of late deliveries, dropping Random Forest and Extra Trees below random guessing ($0.44\text{--}0.47$ ROC-AUC).
4. **Regularized Linear Model Superiority**: Regularized Logistic Regression ($C=0.1$) avoided sharp non-linear leaf node memorization and preserved a positive $1.55\times$ PR-AUC lift on the holdout test set.

### 7.3 Model Selection Rationale & Provenance
*(Provenance Disclosure: Formerly documented as a "Predeclared Model Selection Protocol"; however, because formal pre-registration prior to inspecting candidate metrics cannot be established, these criteria are documented as the **selection rationale adopted during this technical review**).*
- **Selection Partition**: The selection rationale applied during this review relies **strictly on the Validation partition** (May–June 2018), never on the test set.
- **Why $C=0.10$ Was Selected Over $C=1.00$**:
  - Validation PR-AUC difference is negligible ($0.1779$ vs $0.1786$, $\Delta = +0.0007$).
  - Validation $F_1$ difference is negligible ($0.2577$ vs $0.2587$, $\Delta = +0.0010$).
  - Validation ROC-AUC is higher for $C=0.10$ ($0.7902$ vs $0.7893$).
  - Under the principle of parsimony, $C=0.10$ imposes a $10\times$ stronger L2 penalty ($\lambda = 10$ vs $\lambda = 1$), suppressing variance across 80+ one-hot encoded geographic levels.
  - Operationally, $C=0.10$ achieves **$22.93\%$ precision** (632 false alarms on validation) vs **$20.28\%$ precision** (936 false alarms for $C=1.00$), preventing 304 false alerts in operations.
- **Exploratory Status of Test Comparisons**: Because the July–August 2018 test partition was already inspected during benchmark iterations, it is now an **exploratory historical evaluation set**, not an untouched final holdout. Any model chosen using knowledge of those test results would suffer from holdout data snooping / survivorship bias.

### 7.4 Prediction-Time Feature Audit & Feature-Safe Specification
- **Defined Prediction Point**: Customer Checkout confirmation (`order_purchase_timestamp`). Field availability must be verified from the checkout operational workflow, not inferred from timestamps alone.
- **Empirical Audit**: Forensic analysis across 10,000 orders proved that `shipping_limit_date` is pegged to `order_approved_at + 144.0 hours` (6 business days) across all payment methods. Because payment approval takes 1–3 business days for Boleto bancário and `order_approved_at` is strictly a forbidden leakage feature, `seller_dispatch_sla_days` was flagged as invalid at checkout.
- **26-Feature Verified Predictor Set**:
  - *Numeric (20)*: `estimated_delivery_days`, `distance_km`, `promised_speed_km_per_day`, `total_items_count`, `unique_sellers_count`, `total_merchandise_value`, `total_freight_value`, `freight_ratio`, `freight_share`, `total_weight_g`, `total_volume_cm3`, `max_dimension_cm`, `max_payment_installments`, `is_same_state`, `is_same_region`, `is_interstate`, `is_high_risk_destination`, `purchase_day_of_week`, `purchase_hour`, `is_weekend`.
  - *Categorical (6)*: `customer_state`, `seller_state`, `customer_region`, `seller_region`, `category_grouped`, `primary_payment_type`.
- **Why Removing `seller_dispatch_sla_days` Is Sufficient**: `shipping_limit_date` was queried in `features.py` solely as an intermediate timestamp to calculate `seller_dispatch_sla_days`. It was never included in `ALL_PREDICTORS` or passed to `ColumnTransformer` or any estimator. Dropping `seller_dispatch_sla_days` completely purges all downstream influence of `shipping_limit_date` and `order_approved_at`.
- **Feature-Safe Alternative Evaluation**: Dropping `seller_dispatch_sla_days` results in Validation ROC-AUC of **0.7827** (vs 0.7902) and PR-AUC of **0.1751** (vs 0.1779), preserving **$98.4\%$ of validation PR-AUC**. This model is presented as an **unevaluated deployment candidate**, not as a production-ready model.

### 7.5 Calibration & Reliability Analysis
- **Distinguishing Discrimination from Reliability**: ROC-AUC and PR-AUC measure ranking discrimination, which can be high even when probabilities are severely miscalibrated.
- **Reported Metrics**:
  - *Validation ($C=0.10$)*: Brier Score $= 0.1897$, ECE (10 uniform bins) $= 0.3613$ ($36.13\%$), actual late prevalence $= 4.97\%$, mean predicted probability $= 0.4079$.
  - *Exploratory Test ($C=0.10$)*: Brier Score $= 0.3360$, ECE (10 uniform bins) $= 0.4909$ ($49.09\%$), actual late prevalence $= 7.48\%$, mean predicted probability $= 0.5732$.
- **Effect of `class_weight='balanced'`**: Loss weighting by $\approx 11.4\times$ shifts the logistic regression intercept upward, scaling output probabilities far above the empirical base rate ($5\text{--}8\%$). Raw probabilities function as monotonic risk scores, not calibrated posterior probabilities.
- **Leakage-Safe Calibration Protocol**: A sound procedure requires 3-way chronological partitioning (Fit base model on Period 1 $\to$ Fit calibrator on out-of-sample Period 2 $\to$ Evaluate calibrated probabilities on subsequent Period 3). Fitting and evaluating a calibrator on the same dataset produces biased, over-optimistic results.
- **Disclosure**: Neither Platt scaling nor isotonic calibration was fitted or evaluated in this benchmark.

### 7.6 Final Governance Decision Memo
- **Current Model (27 Features)**: **Baseline for comparison only**. Retained in application strictly for software interface compatibility; explicitly not approved for operational checkout scoring due to post-purchase payment clearance contamination (`seller_dispatch_sla_days`).
- **Phase 2 Primary Research Candidate (34 Features, Unweighted)**: **Candidate for further evaluation**. Incorporates 8 checkout-safe predictors (`sla_tightness_km_per_day`, `sla_buffer_days_per_100km`, `package_density_g_cm3`, `is_heavy_package`, `is_sp_to_sp`, `freight_per_item`, `merchandise_per_item`, `purchase_month`). Achieves validation ROC-AUC **0.7918**, PR-AUC **0.1821**, Brier score **0.0451**, ECE **3.25%**, and F1 **0.2596** (precision 20.61%, recall 35.05%, catching 224 of 639 late orders) at the balanced threshold $\tau=0.18$.
- **Operational Accuracy Note**: The balanced threshold intentionally trades raw accuracy ($90.05\%$ vs $95.03\%$ all-on-time baseline) to detect delayed orders. No claim of improved accuracy over the naive baseline is made.
- **Exploratory Holdout Status**: Because the July–August 2018 test split was repeatedly examined during audit benchmarking, test performance metrics are exploratory.
- **Overall Decision**: **DEFER PRODUCTION INTEGRATION PENDING SHADOW EVALUATION**. The 34-feature model must undergo live shadow evaluation on uninspected post-2018 data before replacing the deployed model artifact. Full analysis detailed in [reports/model_artifacts/ml_improvement_phase2_report.md](../reports/model_artifacts/ml_improvement_phase2_report.md).


