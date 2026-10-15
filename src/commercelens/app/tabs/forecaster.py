"""
CommerceLens AI — Delivery Risk Forecaster Tab
==============================================
Point-in-time order risk simulation using the Phase 4 machine learning pipeline.
Enforces strict leakage rejection, discloses temporal validation decay,
and provides operational decision support.
"""

from pathlib import Path
from typing import Any, Dict
import streamlit as st

from commercelens.app.components import metric_card
from commercelens.ml.features import (
    ALL_PREDICTORS,
    BRAZIL_MACRO_REGIONS,
    FORBIDDEN_LEAKAGE_COLUMNS,
    HIGH_RISK_DESTINATIONS,
    validate_no_leakage,
)
from commercelens.ml.predict import DeliveryRiskPredictor, load_delivery_predictor


@st.cache_resource(show_spinner=False)
def get_cached_predictor() -> DeliveryRiskPredictor:
    """Loads and caches the Phase 4 delivery risk model artifact."""
    artifact_dir = Path("reports/model_artifacts")
    return load_delivery_predictor(artifact_dir)


def render_forecaster_tab() -> None:
    """Renders Tab 2: Delivery Risk Forecaster."""
    st.markdown("### 🚚 Delivery Risk Forecaster (Phase 4 ML Pipeline)")
    st.markdown(
        "Predicts the probability that an order will breach its promised delivery SLA using only features "
        "available at the point of purchase checkout. Enforces zero data leakage."
    )

    # 1. Model Status & Governance Disclosure Banner
    with st.expander("ℹ️ Model Architecture & Holdout Validation Governance (Disclosures)", expanded=True):
        st.markdown(
            """
            **Model Artifact**: `reports/model_artifacts/model_pipeline.joblib`  
            **Algorithm**: Regularized Logistic Regression (`C=0.1`, `class_weight='balanced'`)  
            **Operational Decision Threshold**: `τ = 0.72` (Validation F1-optimal)
            """
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Holdout Test ROC-AUC", "0.6112", delta="-0.1790 vs Val (0.7902)", delta_color="normal")
        with c2:
            st.metric("Holdout Test PR-AUC", "0.1157", delta="1.55x lift vs 0.0748 base", delta_color="normal")
        with c3:
            st.metric("Holdout Test Recall", "32.05%", help="300 / 936 late orders flagged")
        with c4:
            st.metric("Holdout Test Precision", "10.37%", help="2,593 false alarms out of 2,893 positive flags")

        st.warning(
            "⚠️ **TEMPORAL GENERALIZATION LIMITATION**: The model exhibits a notable performance decline from "
            "Validation (May–Jun 2018 ROC-AUC 0.7902) to Test (Jul–Aug 2018 ROC-AUC 0.6112). Potential contributing "
            "factors may include macroeconomic shifts, logistical disruptions during the May 2018 Brazilian truck "
            "drivers' strike, and evolving carrier SLA buffers, though direct causality has not been formally isolated "
            "in the dataset. This model provides early warning signals, **not** guaranteed delivery outcomes."
        )

    st.markdown("---")

    # 2. Load Predictor
    try:
        predictor = get_cached_predictor()
    except Exception as e:
        st.error(f"❌ Failed to load model artifact: {e}")
        st.info("Verify that `reports/model_artifacts/model_pipeline.joblib` exists.")
        return

    # 3. Interactive Scenario Configuration Form
    st.markdown("#### Configure Order Simulation Scenario")
    st.caption("Hypothetical test inputs. Manually entered data is evaluated in-memory and never persisted to the database.")

    # Preset selection
    preset = st.radio(
        "Load Preset Scenario:",
        [
            "High-Risk Interstate Long-Haul (SP -> RJ, tight SLA, heavy package)",
            "Low-Risk Local Delivery (SP -> SP, generous SLA, standard parcel)",
            "Custom Order Parameters",
        ],
        horizontal=True,
    )

    if preset == "High-Risk Interstate Long-Haul (SP -> RJ, tight SLA, heavy package)":
        def_cust_state = "RJ"
        def_sell_state = "SP"
        def_est_sla = 8.0
        def_seller_sla = 4.0
        def_dist = 430.0
        def_items = 2
        def_merch = 280.0
        def_freight = 55.0
        def_weight = 4500.0
        def_vol = 24000.0
        def_max_dim = 45.0
        def_cat = "furniture_decor"
        def_pay = "credit_card"
        def_inst = 6
    elif preset == "Low-Risk Local Delivery (SP -> SP, generous SLA, standard parcel)":
        def_cust_state = "SP"
        def_sell_state = "SP"
        def_est_sla = 22.0
        def_seller_sla = 2.0
        def_dist = 45.0
        def_items = 1
        def_merch = 120.0
        def_freight = 15.0
        def_weight = 500.0
        def_vol = 3000.0
        def_max_dim = 20.0
        def_cat = "health_beauty"
        def_pay = "credit_card"
        def_inst = 1
    else:
        def_cust_state = "MG"
        def_sell_state = "SP"
        def_est_sla = 15.0
        def_seller_sla = 3.0
        def_dist = 500.0
        def_items = 1
        def_merch = 150.0
        def_freight = 25.0
        def_weight = 1200.0
        def_vol = 8000.0
        def_max_dim = 30.0
        def_cat = "bed_bath_table"
        def_pay = "credit_card"
        def_inst = 3

    col1, col2, col3 = st.columns(3)

    brazil_states = [
        "SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "ES", "GO", "PE",
        "CE", "PA", "MT", "MA", "MS", "PB", "PI", "RN", "AL", "SE", "TO",
        "RO", "AM", "AC", "AP", "RR",
    ]

    with col1:
        st.markdown("**Geography & Routing**")
        customer_state = st.selectbox("Customer State (Destination)", brazil_states, index=brazil_states.index(def_cust_state))
        seller_state = st.selectbox("Seller State (Origin)", brazil_states, index=brazil_states.index(def_sell_state))
        distance_km = st.number_input("Estimated Distance (km)", min_value=1.0, max_value=4500.0, value=float(def_dist), step=25.0)

    with col2:
        st.markdown("**SLA Commitments**")
        estimated_delivery_days = st.number_input(
            "Promised Delivery SLA (Days)", min_value=1.0, max_value=90.0, value=float(def_est_sla), step=1.0,
            help="Calendar days between purchase timestamp and promised customer arrival date."
        )
        seller_dispatch_sla_days = st.number_input(
            "Seller Dispatch SLA (Days)", min_value=0.5, max_value=30.0, value=float(def_seller_sla), step=0.5,
            help="SLA days for seller to hand parcel over to carrier."
        )
        category = st.selectbox(
            "Primary Product Category",
            [
                "bed_bath_table", "sports_leisure", "health_beauty", "computers_accessories",
                "furniture_decor", "housewares", "watches_gifts", "telephony", "toys",
                "cool_stuff", "garden_tools", "auto", "perfumery", "baby", "electronics", "other",
            ],
            index=0 if def_cat not in ["furniture_decor", "health_beauty"] else (4 if def_cat == "furniture_decor" else 2),
        )

    with col3:
        st.markdown("**Basket & Logistics Physicals**")
        total_items = st.number_input("Items Count", min_value=1, max_value=20, value=int(def_items))
        total_merch = st.number_input("Merchandise Value (R$)", min_value=5.0, max_value=10000.0, value=float(def_merch), step=10.0)
        total_freight = st.number_input("Freight Value (R$)", min_value=0.0, max_value=1000.0, value=float(def_freight), step=5.0)
        total_weight_g = st.number_input("Weight (grams)", min_value=50.0, max_value=40000.0, value=float(def_weight), step=100.0)
        total_vol_cm3 = st.number_input("Volume (cm³)", min_value=100.0, max_value=200000.0, value=float(def_vol), step=500.0)
        max_dim_cm = st.number_input("Max Dimension (cm)", min_value=5.0, max_value=150.0, value=float(def_max_dim), step=5.0)
        payment_type = st.selectbox("Payment Type", ["credit_card", "boleto", "voucher", "debit_card"], index=0)
        installments = st.number_input("Installments", min_value=1, max_value=24, value=int(def_inst))

    # 4. Strict Leakage Guardrail Assertion
    leakage_check_cols = ["order_delivered_customer_date", "is_late", "carrier_transit_days"]
    st.markdown("**Point-in-Time Integrity Audit:**")
    st.caption("Validating zero leakage: all post-purchase operational milestones are excluded from inference.")

    if st.button("🚀 Evaluate Late-Delivery Risk", type="primary", use_container_width=True):
        # Derive point-in-time features explicitly matching ALL_PREDICTORS
        cust_region = BRAZIL_MACRO_REGIONS.get(customer_state, "Other")
        sell_region = BRAZIL_MACRO_REGIONS.get(seller_state, "Other")
        is_same_st = 1 if customer_state == seller_state else 0
        is_same_reg = 1 if cust_region == sell_region else 0
        is_inter = 1 if customer_state != seller_state else 0
        is_high_risk = 1 if customer_state in HIGH_RISK_DESTINATIONS else 0
        freight_ratio = round(total_freight / max(total_merch, 0.01), 4)
        freight_share = total_freight / (total_merch + total_freight + 1e-4)
        promised_speed = distance_km / max(estimated_delivery_days, 1.0)

        feature_dict: Dict[str, Any] = {
            "estimated_delivery_days": float(estimated_delivery_days),
            "seller_dispatch_sla_days": float(seller_dispatch_sla_days),
            "distance_km": float(distance_km),
            "promised_speed_km_per_day": float(promised_speed),
            "total_items_count": int(total_items),
            "unique_sellers_count": 1,
            "total_merchandise_value": float(total_merch),
            "total_freight_value": float(total_freight),
            "freight_ratio": float(freight_ratio),
            "freight_share": float(freight_share),
            "total_weight_g": float(total_weight_g),
            "total_volume_cm3": float(total_vol_cm3),
            "max_dimension_cm": float(max_dim_cm),
            "max_payment_installments": int(installments),
            "is_same_state": is_same_st,
            "is_same_region": is_same_reg,
            "is_interstate": is_inter,
            "is_high_risk_destination": is_high_risk,
            "purchase_day_of_week": 2,  # Wednesday representative
            "purchase_hour": 14,        # 2 PM representative
            "is_weekend": 0,
            "customer_state": customer_state,
            "seller_state": seller_state,
            "customer_region": cust_region,
            "seller_region": sell_region,
            "category_grouped": category,
            "primary_payment_type": payment_type,
        }

        # Assert no leakage
        try:
            validate_no_leakage(feature_dict.keys())
        except ValueError as e:
            st.error(f"Leakage validation failed: {e}")
            return

        # Execute prediction
        result = predictor.predict(feature_dict)
        prob = float(result["late_risk_probability"])
        tier = str(result["risk_tier"])
        is_flagged = bool(result["is_late_risk"])

        st.markdown("---")
        st.markdown("### 📋 Prediction Results & Operational Triage")

        res_c1, res_c2, res_c3 = st.columns(3)
        with res_c1:
            tier_badge = (
                '<span class="badge-danger">HIGH RISK</span>'
                if tier == "HIGH"
                else ('<span class="badge-warning">MEDIUM RISK</span>' if tier == "MEDIUM" else '<span class="badge-success">LOW RISK</span>')
            )
            st.markdown(f"**Risk Tier**: {tier_badge}", unsafe_allow_html=True)
            metric_card("Late Probability", f"{prob * 100:.2f}%", subtitle="Estimated chance of delivery delay")

        with res_c2:
            st.markdown(f"**Decision Threshold**: `τ = {predictor.threshold:.2f}`")
            action_text = "🚨 **FLAGGED FOR INTERVENTION**" if is_flagged else "✅ **STANDARD FULFILLMENT**"
            st.markdown(action_text)
            st.caption(
                f"At τ = {predictor.threshold:.2f}, probability ({prob:.4f}) is "
                f"{'above' if prob >= predictor.threshold else 'below'} the intervention threshold."
            )

        with res_c3:
            st.markdown("**Operational Triage Guidance**:")
            if tier == "HIGH":
                st.error(
                    "• Alert seller for expedited same-day dispatch.\n"
                    "• Route via priority express courier if available.\n"
                    "• Pre-schedule proactive customer status notification."
                )
            elif tier == "MEDIUM":
                st.warning(
                    "• Monitor seller dispatch SLA compliance.\n"
                    "• Standard tracking with automated milestone reminders."
                )
            else:
                st.success(
                    "• Order exhibits healthy SLA buffer and standard corridor dynamics.\n"
                    "• Standard logistics fulfillment flow."
                )
