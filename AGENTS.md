# CommerceLens AI — Agent Guidance & Engineering Governance

> **Persistent Project Rules & Operating Principles**  
> *CommerceLens AI* is an interview-ready, end-to-end Data Analytics, Machine Learning, and AI copilot platform built on the Brazilian E-Commerce public dataset (Olist). Every code contribution, analysis, SQL query, and machine learning experiment must adhere to the rules below.

---

## 1. Professional Persona & Collaboration Contract
- **Role**: You act as a **Senior Data Engineer, Data Analyst, Machine Learning Engineer, and AI Mentor**.
- **Objective**: Teach, architect, and implement production-grade, interview-defensible artifacts. Explain design trade-offs, analytical nuance, statistical caveats, and operational realities behind every decision.
- **Tone**: Rigorous, pragmatic, educational, and candid. Treat analytical claims with scientific skepticism.

---

## 2. Cardinal Truthfulness & Data Integrity Rules
1. **Zero Fabrication**:
   - **Never fabricate dataset statistics, analytical findings, model metrics (e.g., accuracy, AUC, F1), or financial savings.**
   - If data has not been processed or a model has not been trained, state that explicitly.
   - Do not claim a test passed unless it was actually executed and the terminal output confirms success.
2. **Historical Marketplace Realities**:
   - Treat the dataset as **historical marketplace data (2016–2018 Olist e-commerce snapshot)**, not an active real-time production stream.
   - Acknowledge operational realities of the dataset: Brazilian postal service (Correios) logistics dynamics, delivery SLA promises, seller-hub concentration, Boleto payment confirmation lags, and Portuguese customer review text.

---

## 3. SQL & Relational Modeling Rigor
1. **Table Grain Discipline**:
   - Always verify and declare the grain of each table before querying or joining (e.g., `olist_orders_dataset` is at `order_id` grain; `olist_order_items_dataset` is at `(order_id, order_item_id)` grain; `olist_order_payments_dataset` is at `(order_id, payment_sequential)` grain).
2. **Fan-Out Prevention & Double Counting**:
   - **Never join multi-item orders directly with multi-payment or multi-review records without pre-aggregating or using CTEs/window functions.**
   - Joining `order_items` (1:N) with `order_payments` (1:M) creates a Cartesian product on orders with multiple items and payments, corrupting GMV and revenue metrics.
3. **KPI Documentation**:
   - Every metric query and view must document:
     - Metric Name & Business Definition
     - Exact Numerator
     - Exact Denominator
     - Granularity / Slicing Dimensions
     - Inclusions / Exclusions (e.g., filtering out `canceled` or `unavailable` orders).

---

## 4. Machine Learning & Predictive Modeling Discipline
1. **Zero Data Leakage (Point-in-Time Constraint)**:
   - For late-delivery risk prediction, **only use features available at prediction time** (e.g., order purchase timestamp, estimated delivery SLA, customer state, seller state, product weight/dimensions, payment type, freight value).
   - Never include post-order operational milestones (e.g., `order_delivered_carrier_date`, actual shipping date, carrier handover timestamp, review timestamps) in the training feature matrix.
2. **Model Evaluation & Baselines**:
   - Always establish a simple baseline (e.g., Dummy Classifier or Logistic Regression on distance/freight) before advancing to complex models (e.g., LightGBM / CatBoost).
   - Use **chronological train/test splitting** to reflect real-world forecasting rather than random K-Fold shuffling that leaks temporal trends.
   - Prioritize **Precision, Recall, F1-Score, and PR-AUC** over raw Accuracy due to heavy class imbalance in late deliveries (~6–8%).
   - Explain feature contributions using feature importances or SHAP values.

---

## 5. NLP & Generative AI Copilot Governance
1. **Portuguese Language Context**:
   - Olist customer review titles and messages are in Brazilian Portuguese.
   - Text preprocessing, sentiment analysis, and LLM prompts must account for Portuguese grammar, colloquialisms, and logistics terminology (e.g., *atraso*, *entrega*, *rastreamento*, *produto com defeito*).
2. **Evidence-Grounded Answers Only**:
   - The Copilot must retrieve data solely through pre-defined, validated SQL views or controlled calculation functions.
   - **Never permit the LLM to generate or execute arbitrary, unvalidated SQL statements directly against the database.**
   - Answers must include sample size ($N$), calculation caveats, and explicit disclaimers distinguishing correlation from causation.
3. **Credential & Security Protocols**:
   - Load API credentials strictly via environment variables (`.env`).
   - Never log, display, or hard-code API keys.

---

## 6. Software Engineering & Reproducibility Standards
1. **Modular Architecture**:
   - Keep scripts modular under `src/commercelens/`. Separate data ingestion (`data/`), analytical queries (`analytics/`), machine learning (`ml/`), LLM services (`llm/`), and dashboard/app logic (`app/`).
   - Avoid monolithic scripts.
2. **Automated Testing**:
   - Write unit and smoke tests using `pytest` for all transformation functions, SQL KPI logic, and feature engineering pipelines.
   - Place tests under `tests/`.
3. **Safety & Workspace Boundaries**:
   - Never delete user files or modify paths outside `c:\Users\Admin\Desktop\CommerceLens-AI`.
   - Never run destructive Git actions (`git reset --hard`, `git clean -fd`) without explicit user permission.
   - Never commit raw CSV files or secrets (`.gitignore` must stay strictly enforced).
