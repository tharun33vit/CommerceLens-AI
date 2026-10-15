# CommerceLens AI — Machine Learning Audit & Benchmark Report

> **Phase 1 Deliverable**: Comprehensive technical audit of the delivery-risk classification model, empirical diagnosis of the validation-to-test performance degradation, point-in-time feature audit, calibration analysis, candidate benchmark across chronological partitions, and final decision memo.

---

## 1. Executive Summary

This audit rigorously evaluates the CommerceLens AI late-delivery risk prediction model. The stated prediction point is the **customer checkout session** (`order_purchase_timestamp`). The model predicts whether an e-commerce order on Olist will arrive after its promised estimated SLA date ($\text{Actual Delivery Date} > \text{Estimated SLA Date}$).

### Key Benchmark & Audit Takeaways
1. **Validation Performance**: Regularized Logistic Regression ($C = 0.1$, balanced) achieves **ROC-AUC of 0.7902** and **PR-AUC of 0.1779** ($3.58\times$ lift over the majority baseline) on the chronological validation set (May 1 – June 30, 2018).
2. **Exploratory Test Degradation**: On the exploratory historical test partition (July 1 – August 29, 2018), performance drops to **ROC-AUC of 0.6112** and **PR-AUC of 0.1157** ($1.55\times$ lift over baseline).
3. **Tree Model Vulnerability**: Complex tree-based models (Random Forest, Extra Trees, HistGradientBoosting) suffer **severe overfitting and temporal failure** on the exploratory test partition:
   - Random Forest ($d=8$) drops from Val ROC-AUC 0.7275 to **Test ROC-AUC 0.4472** (worse than random guessing).
   - Extra Trees ($d=8$) drops to **Test ROC-AUC 0.4422**.
   - HistGradientBoosting ($d=6$) drops from Val ROC-AUC 0.7893 to **Test ROC-AUC 0.5364**.
   - Regularized linear models (Logistic Regression) demonstrate significantly higher stability and generalization resilience.
4. **Current Model Status (Comparison Baseline Only)**: Forensic audit proved that `seller_dispatch_sla_days` depends on post-purchase payment authorization (`order_approved_at + 144.0 hours`). Because the stated prediction point is checkout, the current 27-feature model has post-checkout timing contamination. It is **retained as a comparison baseline only**, not recommended for operational checkout-time scoring.
5. **Feature-Safe Alternative (Unevaluated Deployment Candidate)**: A 26-predictor feature-safe specification (excluding `seller_dispatch_sla_days`) was trained and evaluated on historical splits, preserving **$98.4\%$ of validation PR-AUC** ($0.1751$ vs $0.1779$) without relying on post-purchase payment clearance timings. This model is presented as an **unevaluated deployment candidate**, not as a production-ready model.
6. **Model-Selection Rationale**: The model-selection rules reflect the technical review rationale adopted during this audit: $C=0.10$ was preferred over $C=1.00$ on the validation partition due to parsimony ($10\times$ stronger L2 regularization penalty suppressing coefficient inflation on 80+ categorical dimensions) and superior operational precision ($22.93\%$ vs $20.28\%$, avoiding 304 false alarms). Test set comparisons are strictly exploratory diagnostics.
7. **Probability Calibration Findings**: Ranking metrics (ROC-AUC 0.7902) do not indicate probability reliability. Due to `class_weight='balanced'`, raw predicted probabilities are scaled upward to counter class imbalance, yielding a Validation Expected Calibration Error (ECE) of **$0.3613$** (Brier score $0.1897$) and Test ECE of **$0.4909$** (Brier score $0.3360$). Post-hoc calibration (Platt scaling / isotonic regression) was not applied.

---

## 2. Root Cause Analysis: Why Test Performance Degrades

Our quantitative drift and correlation analysis revealed that the validation-to-test gap is **not** caused by code bugs, target leakage, or random variance. It is driven by a massive, quantifiable **macroeconomic and platform policy regime shift** in Brazil during mid-2018:

### 2.1 The SLA Compression Regime Shift
Between June and August 2018, Olist dramatically altered its promised delivery estimated dates:
- **Historical Train Mean (Sep 2016 – Apr 2018)**: Estimated delivery SLA averaged **$24.58$ days** ($\sigma = 7.99$).
- **Validation Post-Strike Mean (May – Jun 2018)**: Following the nationwide Brazilian truck drivers' strike (*Greve dos Caminhoneiros*, May 21–31, 2018), Olist artificially padded delivery promises; June 2018 estimated delivery SLA rose to **$27.77$ days**, reducing June late rate to an all-time low of **$1.36\%$**.
- **Exploratory Test Partition Mean (Jul – Aug 2018)**: In July and August 2018, Olist aggressively compressed customer SLA dates. Estimated delivery SLA collapsed to **$19.69$ days in July** and **$15.19$ days in August** (overall test mean: **$17.40$ days**).
- **Quantified Feature Drift**: `estimated_delivery_days` shifted by **$-0.899$ standard deviations** between training and test sets.

```
Monthly Average Estimated Delivery SLA vs Actual Delivery Days:
  Month       Orders    Avg Actual Days    Avg Estimated Days    Net Buffer Days
  2018-03      7,003        16.30 days         22.03 days          +5.73 days
  2018-04      6,798        11.50 days         23.68 days         +12.18 days
  2018-05      6,749        11.42 days         22.89 days         +11.47 days (Truck strike)
  2018-06      6,096         9.24 days         27.77 days         +18.53 days (High buffer)
  2018-07      6,156         8.96 days         19.69 days         +10.73 days (Buffer cut)
  2018-08      6,351         7.73 days         15.19 days          +7.45 days (Aggressive SLA)
```

### 2.2 Inversion of Intra-State vs Inter-State Risk
Because Olist compressed estimated delivery promises most severely on local, short-distance routes, historical geographic risk patterns completely inverted:
- **Training Set (2016 – Apr 2018)**:
  - Interstate orders (`is_same_state == 0`): Late rate was **$10.62\%$** (high risk).
  - Intra-state orders (`is_same_state == 1`): Late rate was **$5.29\%$** (low risk).
  - Correlation between `is_same_state` and `is_late`: **$-0.0895$**.
- **Validation Set (May – Jun 2018)**:
  - Interstate orders: Late rate was **$6.01\%$**.
  - Intra-state orders: Late rate was **$3.40\%$**.
  - Correlation: **$-0.0588$**.
- **Exploratory Test Partition (Jul – Aug 2018)**:
  - Interstate orders: Late rate dropped to **$4.06\%$**!
  - Intra-state orders: Late rate spiked to **$12.35\%$**!
  - Correlation between `is_same_state` and `is_late` completely inverted to **$+0.1551$**!
  - Specifically, for São Paulo local orders (`SP -> SP`), the late rate surged from **$3.44\%$ in validation** to **$12.58\%$ in the test set** because average promised delivery SLA was slashed from $17.87$ days down to **$10.93$ days**.
  - Intra-state orders accounted for **$68.2\%$ of all late deliveries** in the test set (638 of 936).

### 2.3 Why Tree Models Collapsed (ROC-AUC < 0.50)
Tree-based models (Random Forest, Extra Trees, HistGradientBoosting) partition the feature space into non-linear orthogonal splits. During training, the trees learned that `distance_km < 350`, `is_same_state == 1`, and `customer_state == 'SP'` constituted virtually "zero-risk" leaf nodes. When platform logistics policies shortened the SLA in August 2018, those exact leaf nodes experienced the highest concentration of late deliveries. The trees assigned them very low probabilities, inverting the risk ordering and resulting in Test ROC-AUCs between $0.44$ and $0.47$.

In contrast, L2-regularized Logistic Regression maintained a smooth linear boundary without pure sub-region partitioning, preserving positive discrimination (Exploratory Test ROC-AUC $0.6112$, Test PR-AUC $0.1157$).

---

## 3. Prediction-Time Feature & Strict Feature Leakage Audit

### 3.1 Defined Prediction Point
The defined operational prediction point is **Customer Checkout (`order_purchase_timestamp`)**. At this instant, the customer is in the cart/checkout interface, before payment confirmation or carrier logistics events take place. Field availability must be verified from the checkout operational workflow, not inferred from timestamps alone.

### 3.2 Forensic Audit of `shipping_limit_date` and `seller_dispatch_sla_days`
A rigorous operational audit was performed to determine whether `shipping_limit_date` and its derived duration `seller_dispatch_sla_days = (shipping_limit_date - order_purchase_timestamp)` were genuinely available at checkout:

1. **Timestamp Occurrence vs Prediction Availability**:
   - In Olist data, `shipping_limit_date` is recorded on line items in `olist_order_items_dataset`. It always occurs chronologically after `order_purchase_timestamp`.
   - However, a timestamp occurring after purchase does **not** prove that the value was known or determined during the checkout session.
2. **Post-Purchase Payment Approval Dependency**:
   - Analysis of $10,000$ verified orders across payment methods revealed that `shipping_limit_date` is pegged to payment authorization (`order_approved_at`), NOT checkout:
     $$\text{shipping\_limit\_date} \approx \text{order\_approved\_at} + 144.0\text{ hours (6 business days)}$$
   - Across all payment methods, the median difference between `shipping_limit_date` and `order_approved_at` is **exactly 144.00 hours** ($6.00$ calendar days):
     - **Credit Card**: Median approval delay $= 0.27$ hours; median `shipping_limit_date - purchase` $= 144.21$ hours.
     - **Boleto Bancário**: Median approval delay $= 30.09$ hours (~1.25 days); median `shipping_limit_date - purchase` $= 174.92$ hours (~7.3 days).
     - **Debit Card**: Median approval delay $= 0.83$ hours; median `shipping_limit_date - purchase` $= 144.29$ hours.
     - **Voucher**: Median approval delay $= 0.28$ hours; median `shipping_limit_date - purchase` $= 144.19$ hours.
3. **Leakage Implication**:
   - At checkout, payment approval has not yet taken place. For Boleto orders, bank clearance takes 1–3 business days.
   - `order_approved_at` is explicitly classified as a **forbidden leakage feature** in `FORBIDDEN_LEAKAGE_COLUMNS` (`src/commercelens/ml/features.py`).
   - Because `seller_dispatch_sla_days` incorporates the payment clearance duration (`order_approved_at - order_purchase_timestamp`), it inadvertently leaks post-checkout payment clearance latency into the checkout prediction matrix.
   - **Audit Verdict**: `shipping_limit_date` and `seller_dispatch_sla_days` are **FLAGGED** as invalid for checkout-time prediction.

### 3.3 Verification of the Feature-Safe Specification (26 Predictors)
To establish a strictly checkout-compliant specification, we verified the availability of all remaining 26 predictors at the defined prediction point (`order_purchase_timestamp`):

#### Numeric Features (20 Predictors)
1. `estimated_delivery_days`: Calendar duration in days of promised delivery window `(order_estimated_delivery_date - order_purchase_timestamp)`. Quoted to customer before checkout confirmation.
2. `distance_km`: Geodesic Haversine distance between customer zip centroid and primary seller zip centroid. Available at checkout via catalog merchant zip and customer shipping address zip.
3. `promised_speed_km_per_day`: `distance_km / estimated_delivery_days`. Derived strictly from known checkout fields.
4. `total_items_count`: Count of item lines in shopping cart at purchase.
5. `unique_sellers_count`: Number of distinct merchants in cart at purchase.
6. `total_merchandise_value`: Shopping cart item subtotal in BRL at checkout.
7. `total_freight_value`: Shipping charge quoted and accepted at checkout in BRL.
8. `freight_ratio`: `total_freight_value / total_merchandise_value`. Point-in-time pricing ratio.
9. `freight_share`: `total_freight_value / (total_merchandise_value + total_freight_value)`. Point-in-time cost intensity.
10. `total_weight_g`: Aggregate catalog weight in grams of products in cart.
11. `total_volume_cm3`: Aggregate package volume ($L \times W \times H$) in $\text{cm}^3$ from catalog attributes.
12. `max_dimension_cm`: Maximum single package dimension from catalog attributes.
13. `max_payment_installments`: Number of credit card installments selected by customer in the checkout payment UI.
14. `is_same_state`: Binary indicator whether customer state equals primary seller state.
15. `is_same_region`: Binary indicator whether customer macro-region equals seller macro-region.
16. `is_interstate`: Binary indicator for cross-border state shipping.
17. `is_high_risk_destination`: Binary indicator whether customer destination state belongs to historically high-friction Correios logistics corridors.
18. `purchase_day_of_week`: Day of week ($0 = \text{Monday}$) extracted from `order_purchase_timestamp`.
19. `purchase_hour`: Hour of day ($0\dots 23$) extracted from `order_purchase_timestamp`.
20. `is_weekend`: Binary indicator for Saturday/Sunday purchase time.

#### Categorical Features (6 Predictors)
21. `customer_state`: Destination state (e.g. SP, RJ, MG) from customer shipping address.
22. `seller_state`: Origin state from merchant registered location.
23. `customer_region`: Brazilian geographic macro-region mapped deterministically from `customer_state`.
24. `seller_region`: Macro-region mapped deterministically from `seller_state`.
25. `category_grouped`: Dominant item product category (top 15 training categories, remainder 'other') from product catalog.
26. `primary_payment_type`: Payment method chosen at checkout (`credit_card`, `boleto`, `voucher`, `debit_card`).

#### Why Removing `seller_dispatch_sla_days` Is Sufficient
In the codebase (`src/commercelens/ml/features.py`), `shipping_limit_date` was queried from `fact_order_items` solely as an intermediate timestamp to calculate `seller_dispatch_sla_days = (shipping_limit_date - order_purchase_timestamp)`. `shipping_limit_date` itself was **never** included in `NUMERIC_FEATURES`, `CATEGORICAL_FEATURES`, or `ALL_PREDICTORS`, and was never passed into `ColumnTransformer` or any model estimator. Therefore, excluding `seller_dispatch_sla_days` completely removes all downstream influence of `shipping_limit_date` and post-purchase payment clearance timing (`order_approved_at`) from the model pipeline.

### 3.4 Evaluation of Feature-Safe Alternative (26 Predictors)
A feature-safe pipeline using strictly the 26 verified predictors was trained on `Train` ($71,118$ rows) and evaluated against validation and exploratory test partitions:

| Feature Set | Regularization ($C$) | Val ROC-AUC | Val PR-AUC | Val Brier | Val ECE | Val Opt $\tau$ | Val Opt $F_1$ | Val Opt Prec | Val Opt Rec | Test ROC-AUC* | Test PR-AUC* | Test Opt $F_1$* |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline (27 Predictors) [Comparison Only]** | $C=0.01$ | $0.7924$ | $0.1718$ | $0.1889$ | $0.3616$ | $0.66$ | $0.2458$ | $0.1879$ | $0.3552$ | $0.6141$ | $0.1124$ | $0.1494$ |
| **Baseline (27 Predictors) [Comparison Only]** | $C=0.10$ | **0.7902** | **0.1779** | $0.1897$ | $0.3613$ | **0.72** | **0.2577** | **0.2293** | $0.2942$ | **0.6112** | **0.1157** | **0.1567** |
| **Baseline (27 Predictors) [Comparison Only]** | $C=1.00$ | $0.7893$ | **0.1786** | $0.1897$ | $0.3610$ | $0.68$ | **0.2587** | $0.2028$ | **0.3568** | $0.6102$ | **0.1162** | $0.1538$ |
| **Feature-Safe (26 Predictors) [Candidate]** | $C=0.01$ | $0.7847$ | $0.1694$ | $0.1954$ | $0.3694$ | $0.68$ | $0.2433$ | $0.1920$ | $0.3318$ | $0.6022$ | $0.1100$ | $0.1448$ |
| **Feature-Safe (26 Predictors) [Candidate]** | $C=0.10$ | **0.7827** | **0.1751** | $0.1962$ | $0.3691$ | **0.69** | **0.2568** | **0.2037** | **0.3474** | **0.5991** | **0.1133** | **0.1503** |
| **Feature-Safe (26 Predictors) [Candidate]** | $C=1.00$ | $0.7811$ | **0.1766** | $0.1964$ | $0.3691$ | $0.69$ | **0.2595** | $0.2049$ | **0.3537** | $0.5977$ | **0.1141** | $0.1511$ |

*\*Note: Test metrics are exploratory holdout diagnostics.*

#### Analytical Assessment of Feature-Safe Alternative
1. **Performance Preservation**: Dropping `seller_dispatch_sla_days` reduces validation PR-AUC by only **$0.0028$** ($0.1751$ vs $0.1779$, a $1.57\%$ relative drop) for $C=0.10$. Validation $F_1$-score drops by only **$0.0009$** ($0.2568$ vs $0.2577$).
2. **Current Status**: The 26-feature model is an **unevaluated deployment candidate**. While point-in-time safe on historical data, it has not undergone live shadow evaluation or temporal calibration, and is not recommended as ready for production integration.

---

## 4. Chronological Splitting & Population Summary

The dataset was sorted strictly by `order_purchase_timestamp` and partitioned into non-overlapping chronological segments:

| Split Partition | Calendar Window | Observations ($N$) | Proportion | Late Orders ($N$) | Late Prevalence |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Train Split** | 2016-09-15 to 2018-04-30 | $71,118$ | $73.72\%$ | $6,251$ | **$8.79\%$** |
| **Validation Split** | 2018-05-01 to 2018-06-30 | $12,845$ | $13.32\%$ | $639$ | **$4.97\%$** |
| **Exploratory Test Partition** | 2018-07-01 to 2018-08-29 | $12,507$ | $12.96\%$ | $936$ | **$7.48\%$** |
| **Total Supervised Population**| **2016-09-15 to 2018-08-29** | **$96,470$** | **$100.00\%$** | **$7,826$** | **$8.11\%$** |

*Integrity Check*: Exactly 0 overlapping order IDs across partitions; timestamps are strictly monotonically non-decreasing across splits.

---

## 5. Candidate Models Benchmark Results & Model-Selection Rationale

### 5.1 Model Selection Rationale Adopted During Review
*(Provenance Disclosure: Formerly documented as a "Predeclared Model Selection Protocol"; however, because formal pre-registration prior to inspecting any candidate metrics cannot be established, these criteria are more accurately documented as the **selection rationale adopted during this technical review**).*

The selection rationale applied during this review rests on the following principles:
1. **Partition Isolation**: Model selection rationale relies **strictly on performance on the Validation split** (May 1 – June 30, 2018). The test partition is not used for hyperparameter selection or architecture ranking.
2. **Primary Selection Criteria**: Maximization of Validation PR-AUC and Validation $F_1$-score at the validation-optimal threshold.
3. **Parsimony Tie-Breaking Rule**: When validation PR-AUC and $F_1$-scores between two candidate models are within a negligible statistical margin ($\Delta \le 0.005$), the principle of parsimony favors the model with **stronger regularization penalty** to minimize variance and prevent coefficient inflation on sparse high-cardinality categorical levels.
4. **Operational Precision Constraint**: When $F_1$ is comparable, the candidate achieving higher operational precision is prioritized to minimize costly false alarms in operational workflows.

### 5.2 Why $C=0.1$ Was Selected Over $C=1.0$ Within the Review Rationale
Although Logistic Regression with $C=1.00$ exhibits marginally higher validation PR-AUC ($0.1786$ vs $0.1779$, $\Delta = +0.0007$) and $F_1$ ($0.2587$ vs $0.2577$, $\Delta = +0.0010$), **$C=0.10$ was preferred** based on the review rationale:
- **Difference is Statistically Negligible**: The $+0.0007$ PR-AUC difference represents less than $0.4\%$ relative variance, well below the $\Delta \le 0.005$ equivalence margin.
- **Validation ROC-AUC is Higher for $C=0.1$**: $C=0.10$ achieves **$0.7902$** vs $0.7893$ for $C=1.00$.
- **Ten-Fold Regularization Strength**: In scikit-learn L2 regularized logistic regression, penalty $\lambda = \frac{1}{C}$. Setting $C=0.10$ enforces $10\times$ stronger weight shrinkage ($\lambda = 10$) than $C=1.00$ ($\lambda = 1$). With 80+ one-hot encoded categories (including 27 Brazilian origin states and 27 destination states), stronger shrinkage suppresses extreme weights on sparse state-to-state corridors (e.g. Acre, Roraima, Amapá), preventing variance inflation under temporal distribution shifts.
- **Substantially Lower False Alarm Volume**: At its validation-optimal threshold ($\tau=0.72$), $C=0.10$ achieves **$22.93\%$ precision** with 632 false alarms. In contrast, $C=1.00$ at its optimal threshold ($\tau=0.68$) achieves only **$20.28\%$ precision** with 936 false alarms. $C=0.10$ eliminates **304 operational false alarms** (a $32.5\%$ reduction in false alerts) for a minor recall variance.

### 5.3 Candidate Architecture Benchmark Table

All candidate models were trained strictly on `Train`. Thresholds were tuned strictly on `Validation`. The reported test set metrics are **strictly exploratory diagnostics** (see Section 5.4):

| Model Architecture | Train Time | Val ROC-AUC | Val PR-AUC | Val Opt $\tau$ | Val $F_1$ | Test ROC-AUC* | Test PR-AUC* | Test Opt Prec* | Test Opt Rec* | Test Opt $F_1$* | Test PR Lift* |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Majority Baseline (Dummy)** | $0.8\text{s}$ | $0.5000$ | $0.0497$ | $0.10$ | $0.0000$ | $0.5000$ | $0.0748$ | $0.0000$ | $0.0000$ | $0.0000$ | $1.00\times$ |
| **Logistic Regression ($C=0.01$)** | $2.8\text{s}$ | **0.7924** | $0.1718$ | $0.66$ | $0.2458$ | **0.6141** | $0.1124$ | $0.0936$ | $0.3697$ | $0.1494$ | $1.50\times$ |
| **Logistic Regression ($C=0.1$) [Baseline 27]**| $3.2\text{s}$ | **0.7902** | **0.1779** | **0.72** | **0.2577** | **0.6112** | **0.1157** | **0.1037** | **0.3205** | **0.1567** | **1.55x** |
| **Logistic Regression ($C=1.0$)** | $4.7\text{s}$ | $0.7893$ | **0.1786** | $0.68$ | **0.2587** | $0.6102$ | **0.1162** | $0.0970$ | $0.3718$ | $0.1538$ | $1.55\times$ |
| **Random Forest ($d=8, n=100$)** | $8.7\text{s}$ | $0.7275$ | $0.1284$ | $0.57$ | $0.2086$ | $0.4472$ | $0.0658$ | $0.0626$ | $0.1571$ | $0.0896$ | $0.88\times$ (Failure) |
| **Random Forest ($d=12, n=150$)**| $15.0\text{s}$| $0.7577$ | $0.1374$ | $0.56$ | $0.2316$ | $0.4787$ | $0.0698$ | $0.0630$ | $0.1838$ | $0.0938$ | $0.93\times$ (Failure) |
| **Extra Trees ($d=8, n=100$)** | $11.4\text{s}$| $0.6614$ | $0.1040$ | $0.67$ | $0.1596$ | $0.4422$ | $0.0661$ | $0.0603$ | $0.0705$ | $0.0650$ | $0.88\times$ (Failure) |
| **HistGradientBoosting ($d=4, \text{lr}=0.05$)** | $6.3\text{s}$ | $0.7874$ | $0.1677$ | $0.61$ | $0.2472$ | $0.5240$ | $0.0809$ | $0.0664$ | $0.2692$ | $0.1065$ | $1.08\times$ |
| **HistGradientBoosting ($d=6, \text{lr}=0.05$)** | $7.9\text{s}$ | $0.7893$ | $0.1752$ | $0.64$ | $0.2588$ | $0.5364$ | $0.0818$ | $0.0677$ | $0.2436$ | $0.1059$ | $1.09\times$ |
| **HistGradientBoosting ($d=6, \text{l2}=1.0$)** | $10.2\text{s}$| $0.7906$ | $0.1740$ | $0.68$ | $0.2514$ | $0.5353$ | $0.0800$ | $0.0651$ | $0.1848$ | $0.0962$ | $1.07\times$ |

*\*Note: Test metrics are exploratory holdout diagnostics.*

### 5.4 Exploratory Status of Test Partition Comparisons
- **Cardinal ML Governance Rule**: Models must **never** be selected based on whichever candidate produces the highest score on the test partition. Choosing $C=0.01$ because its test ROC-AUC is $0.6141$ (versus $0.6112$ for $C=0.10$) constitutes post-hoc holdout snooping, destroying the test set's ability to provide an unbiased estimate of future out-of-distribution performance.
- Because the July–August 2018 test partition was already inspected during diagnostic benchmark iterations, it is now an **exploratory historical evaluation set**, NOT an untouched final holdout. Any subsequent model chosen using knowledge of those test results would suffer from holdout data snooping / survivorship bias.

---

## 6. Decision Threshold Analysis & Trade-Offs

Because late deliveries constitute a minority class (~5–9%), setting threshold at $0.50$ (default balanced) produces excessive false alarms. Operational threshold tuning was conducted strictly on the validation set:

### Validation Threshold Sweep (Logistic Regression $C=0.1$)
| Threshold ($\tau$) | Precision | Recall | $F_1$-Score | Accuracy | True Positives | False Positives | False Negatives | True Negatives |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0.30** | $0.0670$ | $0.9781$ | $0.1255$ | $0.3218$ | 625 | 8,698 | 14 | 3,508 |
| **0.40** | $0.0889$ | $0.8670$ | $0.1612$ | $0.5513$ | 554 | 5,679 | 85 | 6,527 |
| **0.50** | $0.1244$ | $0.6651$ | $0.2096$ | $0.7505$ | 425 | 2,991 | 214 | 9,215 |
| **0.60** | $0.1624$ | $0.4710$ | $0.2415$ | $0.8528$ | 301 | 1,553 | 338 | 10,653 |
| **0.70** | $0.2115$ | $0.3177$ | $0.2539$ | $0.9071$ | 203 | 757 | 436 | 11,449 |
| **0.72** [Selected] | **0.2293** | **0.2942** | **0.2577** | **0.9157** | **188** | **632** | **451** | **11,574** |
| **0.80** | $0.2641$ | $0.1393$ | $0.1824$ | $0.9379$ | 89 | 248 | 550 | 11,958 |

### Exploratory Test Evaluation Across Thresholds
| Threshold ($\tau$) | Precision | Recall | $F_1$-Score | Caught Delays (TP) | False Alarms (FP) | Missed Delays (FN) | True On-Time (TN) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0.50** (Default) | $0.0943$ | **0.7682** | **0.1680** | **719** | 6,904 | 217 | 4,667 |
| **0.60** | $0.0921$ | $0.5000$ | $0.1556$ | 468 | 4,611 | 468 | 6,960 |
| **0.72** (Validation-Selected)| **0.1037** | **0.3205** | **0.1567** | **300** | **2,593** | **636** | **8,978** |
| **0.80** | $0.1208$ | $0.2190$ | $0.1557$ | 205 | 1,492 | 731 | 10,079 |
| **0.85** | $0.1431$ | $0.1613$ | $0.1517$ | 151 | 904 | 785 | 10,667 |

**Operational Trade-off Defense**:
- At threshold `0.50`, the model captures $76.8\%$ of late orders, but generates $6,904$ false alarms (a false-alarm-to-true-delay ratio of $9.6 : 1$).
- At the validation-selected threshold `0.72`, false alarms drop by **$62.4\%$** (from $6,904$ to $2,593$), while still detecting $32.1\%$ of late deliveries ($300$ caught delays).
- For automated customer communications, a higher threshold ($\tau \ge 0.80$) should be chosen to keep false alarms below $1,500$.

---

## 7. Calibration & Probability Reliability Analysis

### 7.1 Distinguishing Ranking Metrics from Calibration Reliability
A fundamental tenet of machine learning governance is the distinction between **ranking discrimination** and **probability calibration**:
- **Ranking Metrics (ROC-AUC & PR-AUC)** measure discrimination—the probability that a randomly chosen late order receives a higher risk score than a randomly chosen on-time order. Logistic Regression achieves solid validation discrimination (ROC-AUC $0.7902$, PR-AUC $0.1779$, a $3.58\times$ lift over baseline).
- **Probability Calibration (Reliability)** measures whether an order assigned a predicted probability of $p$ actually has an empirical failure frequency equal to $p$. A model can have high ROC-AUC while producing severely miscalibrated probabilities.

### 7.2 Quantitative Calibration Metrics
| Model & Partition | Brier Score | Expected Calibration Error (ECE, 10 Bins) | Actual Late Prevalence | Mean Predicted Probability |
| :--- | :---: | :---: | :---: | :---: |
| **Validation ($C=0.10$, Baseline 27)** | **0.1897** | **0.3613** ($36.13\%$) | **$4.97\%$** ($639 / 12,845$) | **$0.4079$** |
| **Validation ($C=0.10$, Feature-Safe 26)**| **0.1962** | **0.3691** ($36.91\%$) | **$4.97\%$** ($639 / 12,845$) | **$0.4158$** |
| **Exploratory Test ($C=0.10$, Baseline 27)** | **0.3360** | **0.4909** ($49.09\%$) | **$7.48\%$** ($936 / 12,507$) | **$0.5732$** |
| **Exploratory Test ($C=0.10$, Feature-Safe 26)**| **0.3402** | **0.4937** ($49.37\%$) | **$7.48\%$** ($936 / 12,507$) | **$0.5765$** |

### 7.3 Effect of `class_weight='balanced'` on Probability Interpretation
In scikit-learn, setting `class_weight='balanced'` weights the loss for each sample inversely proportional to class frequencies:
$$w_1 = \frac{N}{2 \times N_{\text{pos}}} \approx \frac{71,118}{2 \times 6,251} \approx 5.69, \quad w_0 = \frac{N}{2 \times N_{\text{neg}}} \approx 0.55$$
The relative weighting of $\approx 11.4 : 1$ shifts the estimated intercept $\beta_0$ upward, scaling raw output sigmoid probabilities $\hat{p} = \sigma(X\beta)$ into a range centered around $0.40\text{--}0.57$, far above the historical late-delivery base rate ($5\text{--}8\%$).
**Crucial Governance Takeaway**: Raw predicted probabilities cannot be interpreted as true posterior probabilities $P(\text{Late} = 1 \mid X)$. They must be treated strictly as **monotonic risk scores**.

### 7.4 Validation Reliability Table (10 Uniform Bins, Baseline $C=0.10$)
The validation calibration curve exhibits **strict monotonic ordering**, confirming strong discriminative ranking despite probability scale inflation:

| Bin | Probability Range | Observations ($N$) | Proportion | Mean Predicted Prob | Empirical Late Rate | Calibration Gap |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | $[0.0, 0.1)$ | 248 | $1.93\%$ | $0.0688$ | **0.0000** | $0.0688$ |
| **2** | $[0.1, 0.2)$ | 1,001 | $7.79\%$ | $0.1588$ | **0.0010** | $0.1578$ |
| **3** | $[0.2, 0.3)$ | 2,273 | $17.70\%$ | $0.2542$ | **0.0057** | $0.2485$ |
| **4** | $[0.3, 0.4)$ | 3,090 | $24.06\%$ | $0.3519$ | **0.0230** | $0.3289$ |
| **5** | $[0.4, 0.5)$ | 2,817 | $21.93\%$ | $0.4452$ | **0.0458** | $0.3995$ |
| **6** | $[0.5, 0.6)$ | 1,562 | $12.16\%$ | $0.5461$ | **0.0794** | $0.4668$ |
| **7** | $[0.6, 0.7)$ | 894 | $6.96\%$ | $0.6469$ | **0.1096** | $0.5373$ |
| **8** | $[0.7, 0.8)$ | 623 | $4.85\%$ | $0.7459$ | **0.1830** | $0.5629$ |
| **9** | $[0.8, 0.9)$ | 290 | $2.26\%$ | $0.8433$ | **0.2483** | $0.5950$ |
| **10**| $[0.9, 1.0)$ | 47 | $0.37\%$ | $0.9284$ | **0.3617** | $0.5667$ |

### 7.5 Exploratory Test Reliability Table (10 Uniform Bins, Baseline $C=0.10$)
On the exploratory test partition, the SLA compression shock (which caused SP-to-SP local orders to fail unexpectedly) produces **non-monotonic flattening** in the mid-to-high risk bins $[0.5, 0.9)$:

| Bin | Probability Range | Observations ($N$) | Proportion | Mean Predicted Prob | Empirical Late Rate | Calibration Gap |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | $[0.0, 0.1)$ | 91 | $0.73\%$ | $0.0632$ | **0.0000** | $0.0632$ |
| **2** | $[0.1, 0.2)$ | 276 | $2.21\%$ | $0.1571$ | **0.0036** | $0.1535$ |
| **3** | $[0.2, 0.3)$ | 551 | $4.41\%$ | $0.2550$ | **0.0145** | $0.2405$ |
| **4** | $[0.3, 0.4)$ | 1,371 | $10.96\%$ | $0.3558$ | **0.0226** | $0.3332$ |
| **5** | $[0.4, 0.5)$ | 2,595 | $20.75\%$ | $0.4526$ | **0.0682** | $0.3844$ |
| **6** | $[0.5, 0.6)$ | 2,544 | $20.34\%$ | $0.5477$ | **0.0987** | $0.4490$ |
| **7** | $[0.6, 0.7)$ | 1,891 | $15.12\%$ | $0.6487$ | **0.0830** | $0.5656$ |
| **8** | $[0.7, 0.8)$ | 1,491 | $11.92\%$ | $0.7492$ | **0.0711** | $0.6781$ |
| **9** | $[0.8, 0.9)$ | 1,142 | $9.13\%$ | $0.8459$ | **0.0946** | $0.7514$ |
| **10**| $[0.9, 1.0)$ | 555 | $4.44\%$ | $0.9375$ | **0.1748** | $0.7627$ |

### 7.6 Leakage-Safe Temporal Calibration Procedure
Fitting a calibrator (such as Platt scaling or isotonic regression) and evaluating it on the exact same dataset produces artificially optimistic calibration scores and constitutes data leakage. A valid, leakage-safe temporal calibration procedure requires:
1. **Three-Way Chronological Partitioning**:
   - **Split 1 (Base Estimator)**: Fit the base feature pipeline and classifier on historical orders (e.g., Inception through December 2017).
   - **Split 2 (Calibration Set)**: Generate out-of-sample predicted scores on a contiguous intermediate calibration partition (e.g., January through April 2018), and fit a monotonic calibrator (such as Platt sigmoid scaling, Isotonic Regression, or Beta Calibration) to map raw scores to empirical probabilities.
   - **Split 3 (Evaluation Set)**: Evaluate the pipeline + calibrator strictly on subsequent chronological data (e.g., May through June 2018) to measure out-of-sample ECE and Brier score.
2. **Rolling-Origin Time-Series Cross-Validation**: Alternatively, perform expanding-window time-series splits within training data, pool the out-of-fold predictions, fit the calibrator, and evaluate on untouched future windows.

#### Non-Calculated Calibration Disclosure
- **Platt Scaling & Isotonic Calibration Were NOT Fitted or Evaluated**: No post-hoc calibrator was fitted or evaluated in this benchmark. The metrics reported above reflect uncalibrated balanced-loss model outputs.

---

## 8. Model Interpretability & Feature Contributions

### Top 15 Predictor Coefficients (Logistic Regression $C = 0.1$)
| Rank | Feature | Standardized Coef | Odds Ratio | Directional Risk Contribution |
| :---: | :--- | :---: | :---: | :--- |
| **1** | `seller_state_MA` | $+0.8400$ | $2.3163$ | Increases Late Risk |
| **2** | `seller_state_PE` | $-0.8250$ | $0.4382$ | Decreases Late Risk |
| **3** | `customer_state_AL` | $+0.7944$ | $2.2130$ | Increases Late Risk |
| **4** | `promised_speed_km_per_day` | $+0.7364$ | $2.0884$ | Increases Late Risk |
| **5** | `distance_km` | $-0.5150$ | $0.5975$ | Decreases Late Risk (conditional on speed) |
| **6** | `seller_state_RS` | $-0.5003$ | $0.6063$ | Decreases Late Risk |
| **7** | `seller_state_BA` | $-0.4883$ | $0.6136$ | Decreases Late Risk |
| **8** | `estimated_delivery_days` | $-0.4867$ | $0.6146$ | Decreases Late Risk (generous SLA buffer) |
| **9** | `customer_state_RR` | $+0.4777$ | $1.6124$ | Increases Late Risk |
| **10**| `customer_state_PR` | $-0.4736$ | $0.6227$ | Decreases Late Risk |
| **11**| `customer_state_PI` | $-0.4307$ | $0.6501$ | Decreases Late Risk |
| **12**| `is_high_risk_destination` | $+0.3865$ | $1.4718$ | Increases Late Risk |
| **13**| `seller_state_CE` | $+0.3814$ | $1.4643$ | Increases Late Risk |
| **14**| `seller_region_Central-West` | $-0.3803$ | $0.6836$ | Decreases Late Risk |
| **15**| `category_grouped_cool_stuff`| $-0.3756$ | $0.6869$ | Decreases Late Risk |

> [!WARNING]
> **Causality & Governance Notice**: Coefficients and odds ratios represent historical observational associations under Brazilian Correios postal operating conditions between 2016 and 2018. They do **not** imply causal mechanisms. For instance, charging higher freight or selecting specific payment methods does not *cause* delays; freight value correlates with long-haul transit corridors across difficult geographical topography.

---

## 9. Final Decision Memo & Governance Verdict

### 9.1 Decision Memo Summary
```
TO:         CommerceLens AI Technical Steering Committee & Operations Leadership
FROM:       Lead Data & Machine Learning Governance Review
DATE:       October 14, 2026
SUBJECT:    DELIVERY RISK BENCHMARK REVIEW & FINAL MODEL DISPOSITION
DISPOSITION: DEFER MODEL INTEGRATION PENDING FURTHER EVALUATION.
             - CURRENT 27-FEATURE MODEL: RETAINED AS COMPARISON BASELINE ONLY.
             - PROPOSED 26-FEATURE MODEL: CANDIDATE FOR FURTHER EVALUATION.
```

### 9.2 Model Categorization & Evidence-Based Disposition

#### 1. Current Model ($C=0.10$, 27 Features): Comparison Baseline Only
- **Classification**: **BASELINE FOR COMPARISON ONLY**.
- **Governance Justification**:
  - The stated prediction point is checkout.
  - The feature audit confirmed that `seller_dispatch_sla_days` incorporates post-purchase payment authorization delay (`order_approved_at`).
  - Therefore, the current 27-feature model is **not recommended for operational checkout-time scoring**.
  - It is retained strictly as a historical benchmark and diagnostic baseline, unless the operational prediction point is explicitly redefined as post-order approval and all predictors are audited at that point.

#### 2. Proposed Model ($C=0.10$, 26 Features): Candidate for Further Evaluation
- **Classification**: **CANDIDATE FOR FURTHER EVALUATION**.
- **Governance Justification**:
  - The 26-feature specification eliminates the flagged post-purchase feature and retains $98.4\%$ of validation PR-AUC ($0.1751$ vs $0.1779$) and $99.6\%$ of validation $F_1$ ($0.2568$ vs $0.2577$).
  - However, this model is **not production-ready**. It has only been evaluated retrospectively on historical splits, lacks temporal probability calibration, and has not been tested in live shadow mode.
  - It serves as the primary candidate specification for future evaluation.

#### 3. Overall Governance Verdict: Defer Model Integration
- **Verdict**: **DEFER MODEL INTEGRATION PENDING FURTHER EVIDENCE**.
- **Disclosed Remaining Limitations**:
  1. **Do Not Retrain Repeatedly Against the Test Set**: Repeated tuning against the July–August 2018 exploratory partition constitutes data snooping and would invalidate holdout independence.
  2. **Do Not Claim Production Readiness Based on Benchmark Scores Alone**: With an exploratory test ROC-AUC of $0.5991\text{--}0.6112$ and ECE of $0.4909$, the model is vulnerable to platform SLA compression shocks.
  3. **Severe Probability Miscalibration**: Without temporal probability calibration, raw model outputs cannot support automated customer-facing delivery promises or financial SLA deductions against sellers.
  4. **Unbiased Holdout Requirement**: Production readiness requires deploying the candidate model in shadow mode against live data or testing against an uninspected future temporal holdout partition.
