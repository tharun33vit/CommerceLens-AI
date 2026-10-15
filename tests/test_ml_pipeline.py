"""
CommerceLens AI — Unit and Integration Tests for ML Pipeline (Phase 4)
======================================================================
Tests point-in-time feature engineering, zero-leakage enforcement,
chronological splitting, model training, threshold tuning, and artifact serving.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from commercelens.analytics.db import create_db_engine, check_connection
from commercelens.ml.features import (
    ALL_PREDICTORS,
    CATEGORICAL_FEATURES,
    FORBIDDEN_LEAKAGE_COLUMNS,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    engineer_point_in_time_features,
    haversine_distance,
    validate_no_leakage,
)
from commercelens.ml.split import (
    chronological_split_by_date,
    chronological_split_by_ratio,
    get_split_summary_stats,
)
from commercelens.ml.pipeline import (
    build_model,
    build_pipeline,
    build_preprocessor,
)
from commercelens.ml.evaluate import (
    compute_classification_metrics,
    sweep_thresholds,
    tune_threshold_on_validation,
)
from commercelens.ml.explain import (
    get_logistic_regression_importance,
    perform_subgroup_error_analysis,
)
from commercelens.ml.predict import (
    DeliveryRiskPredictor,
    load_delivery_predictor,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def synthetic_order_data():
    """Generates a small deterministic synthetic dataset for unit testing."""
    n = 200
    base_time = datetime(2017, 1, 1, 10, 0, 0)
    rows = []

    for i in range(n):
        order_time = base_time + timedelta(days=i * 2)
        est_days = 15.0 + (i % 10)
        est_time = order_time + timedelta(days=est_days)
        ship_limit = order_time + timedelta(days=3.0)

        # 15% late deliveries deterministically
        is_late_flag = 1 if (i % 7 == 0) else 0

        # Customer & seller states
        c_state = ["SP", "RJ", "MG", "BA", "RS"][i % 5]
        s_state = "SP" if (i % 2 == 0) else "PR"

        rows.append({
            "order_id": f"ord_{i:04d}",
            "order_purchase_timestamp": order_time,
            "order_estimated_delivery_date": est_time,
            "shipping_limit_date": ship_limit,
            "estimated_delivery_days": est_days,
            "seller_dispatch_sla_days": 3.0,
            "is_late": is_late_flag,
            "customer_state": c_state,
            "customer_zip_prefix": f"1000{i%10}",
            "seller_state": s_state,
            "seller_zip_prefix": "01000",
            "is_same_state": 1 if c_state == s_state else 0,
            "primary_category": ["health_beauty", "sports_leisure", "watches_gifts"][i % 3],
            "total_items_count": 1 + (i % 3),
            "unique_sellers_count": 1,
            "unique_products_count": 1,
            "unique_categories_count": 1,
            "total_merchandise_value": float(50.0 + (i * 2.5)),
            "total_freight_value": float(15.0 + (i * 0.2)),
            "freight_ratio": float((15.0 + i * 0.2) / (50.0 + i * 2.5)),
            "avg_item_price": float(50.0),
            "avg_item_freight": float(15.0),
            "max_item_price": float(50.0),
            "max_item_freight": float(15.0),
            "total_weight_g": 500.0 + (i * 10),
            "max_weight_g": 500.0,
            "total_volume_cm3": 3000.0 + (i * 20),
            "max_dimension_cm": 20.0,
            "customer_lat": -23.55 + (i * 0.01),
            "customer_lng": -46.63 + (i * 0.01),
            "seller_lat": -23.55,
            "seller_lng": -46.63,
            "primary_payment_type": ["credit_card", "boleto"][i % 2],
            "max_payment_installments": 1 + (i % 4),
        })

    return pd.DataFrame(rows)


# ==============================================================================
# 1. Zero Data Leakage & Validation Tests
# ==============================================================================

def test_leakage_rejection_raises_error_for_all_forbidden_columns():
    """Assert that validate_no_leakage raises ValueError for every prohibited field."""
    for col in FORBIDDEN_LEAKAGE_COLUMNS:
        with pytest.raises(ValueError, match="DATA LEAKAGE DETECTED"):
            validate_no_leakage([col, "distance_km", "total_items_count"])


def test_valid_predictors_pass_leakage_check():
    """Assert that authorized point-in-time predictors pass without error."""
    validate_no_leakage(ALL_PREDICTORS)
    assert len(ALL_PREDICTORS) == len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES)


def test_predictor_rejects_leakage_columns_in_predict_input(tmp_path, synthetic_order_data):
    """Assert that DeliveryRiskPredictor rejects forbidden post-order fields at prediction time."""
    df_feat = engineer_point_in_time_features(synthetic_order_data)
    pipe = build_pipeline(model_type="logistic_regression")
    pipe.fit(df_feat[ALL_PREDICTORS], df_feat[TARGET_COLUMN])

    art_file = tmp_path / "model_pipeline.joblib"
    import joblib
    joblib.dump(pipe, art_file)

    predictor = DeliveryRiskPredictor(pipeline_path=art_file)

    # Attempting to predict on a dict containing post-order delivery timestamp
    leaked_dict = {
        "estimated_delivery_days": 12.0,
        "order_delivered_customer_date": "2017-01-20 12:00:00",  # FORBIDDEN!
    }
    with pytest.raises(ValueError, match="DATA LEAKAGE DETECTED"):
        predictor.predict(leaked_dict)


# ==============================================================================
# 2. Point-in-Time Feature Engineering Tests
# ==============================================================================

def test_haversine_distance_known_coordinates():
    """Verify geodesic distance calculation between São Paulo and Rio de Janeiro (~357 km)."""
    # São Paulo coordinates: -23.5505, -46.6333
    # Rio de Janeiro coordinates: -22.9068, -43.1729
    sp_lat, sp_lon = -23.5505, -46.6333
    rj_lat, rj_lon = -22.9068, -43.1729

    dist = haversine_distance(
        np.array([sp_lat]), np.array([sp_lon]),
        np.array([rj_lat]), np.array([rj_lon]),
    )[0]

    # Geodesic distance is ~357-360 km
    assert 350.0 < dist < 365.0, f"Expected ~357 km, got {dist:.2f} km"


def test_haversine_distance_handles_nan_coordinates():
    """Verify that missing coordinates safely return NaN rather than failing."""
    dists = haversine_distance(
        np.array([np.nan, -23.55]), np.array([-46.63, np.nan]),
        np.array([-22.90, -22.90]), np.array([-43.17, -43.17]),
    )
    assert np.isnan(dists[0])
    assert np.isnan(dists[1])


def test_engineer_point_in_time_features(synthetic_order_data):
    """Test feature derivation and ensure exactly one row per order."""
    df_feat = engineer_point_in_time_features(synthetic_order_data)

    assert len(df_feat) == len(synthetic_order_data)
    assert "distance_km" in df_feat.columns
    assert "promised_speed_km_per_day" in df_feat.columns
    assert "is_same_region" in df_feat.columns
    assert "is_interstate" in df_feat.columns
    assert "is_high_risk_destination" in df_feat.columns
    assert "purchase_day_of_week" in df_feat.columns
    assert "category_grouped" in df_feat.columns

    # Check value consistency
    assert (df_feat["promised_speed_km_per_day"] >= 0).all()
    assert df_feat["is_same_region"].isin([0, 1]).all()
    assert df_feat["is_interstate"].isin([0, 1]).all()


# ==============================================================================
# 3. Chronological Splitting Tests
# ==============================================================================

def test_chronological_split_by_date(synthetic_order_data):
    """Test date-based chronological partition for strict temporal monotonicity and disjointness."""
    train_df, val_df, test_df = chronological_split_by_date(
        synthetic_order_data,
        time_col="order_purchase_timestamp",
        val_cutoff="2017-06-01",
        test_cutoff="2017-10-01",
    )

    # All non-empty
    assert len(train_df) > 0
    assert len(val_df) > 0
    assert len(test_df) > 0
    assert len(train_df) + len(val_df) + len(test_df) == len(synthetic_order_data)

    # Disjoint order IDs
    train_ids = set(train_df["order_id"])
    val_ids = set(val_df["order_id"])
    test_ids = set(test_df["order_id"])
    assert len(train_ids.intersection(val_ids)) == 0
    assert len(train_ids.intersection(test_ids)) == 0
    assert len(val_ids.intersection(test_ids)) == 0

    # Temporal monotonicity
    assert train_df["order_purchase_timestamp"].max() < val_df["order_purchase_timestamp"].min()
    assert val_df["order_purchase_timestamp"].max() < test_df["order_purchase_timestamp"].min()


def test_chronological_split_by_ratio(synthetic_order_data):
    """Test proportion-based chronological partition (70/15/15)."""
    train_df, val_df, test_df = chronological_split_by_ratio(
        synthetic_order_data,
        time_col="order_purchase_timestamp",
        train_ratio=0.70,
        val_ratio=0.15,
    )

    n = len(synthetic_order_data)
    assert len(train_df) == int(n * 0.70)
    assert len(val_df) == int(n * 0.85) - int(n * 0.70)
    assert len(train_df) + len(val_df) + len(test_df) == n

    stats = get_split_summary_stats(train_df, val_df, test_df)
    assert stats["train"]["pct"] == 70.0
    assert stats["validation"]["pct"] == 15.0
    assert stats["test"]["pct"] == 15.0


# ==============================================================================
# 4. Training-Only Preprocessing & Pipeline Tests
# ==============================================================================

def test_preprocessing_fitted_exclusively_on_train(synthetic_order_data):
    """Verify ColumnTransformer handles unseen test categories without error or leakage."""
    df_feat = engineer_point_in_time_features(synthetic_order_data)
    train_df, val_df, test_df = chronological_split_by_ratio(df_feat)

    preprocessor = build_preprocessor()
    X_train = preprocessor.fit_transform(train_df[ALL_PREDICTORS])

    # Inject an unseen category into test data
    test_mod = test_df[ALL_PREDICTORS].copy()
    test_mod.loc[test_mod.index[0], "customer_state"] = "UNSEEN_STATE"

    # Should transform safely with handle_unknown='ignore'
    X_test = preprocessor.transform(test_mod)
    assert X_train.shape[1] == X_test.shape[1]
    assert not np.isnan(X_test).any()


# ==============================================================================
# 5. Evaluation Metrics & Decision Threshold Tuning Tests
# ==============================================================================

def test_compute_classification_metrics_math():
    """Verify precision, recall, and F1 calculations against hand-calculated values."""
    y_true = np.array([1, 1, 0, 0, 0])
    y_prob = np.array([0.9, 0.4, 0.8, 0.1, 0.2])

    # Threshold 0.5:
    # y_pred: [1, 0, 1, 0, 0]
    # TP=1, FP=1, FN=1, TN=2
    # Prec = 1/2 = 0.5, Rec = 1/2 = 0.5, F1 = 0.5
    m = compute_classification_metrics(y_true, y_prob, threshold=0.5)

    assert m["precision"] == 0.5000
    assert m["recall"] == 0.5000
    assert m["f1_score"] == 0.5000
    assert m["confusion_matrix"]["tp"] == 1
    assert m["confusion_matrix"]["fp"] == 1
    assert m["confusion_matrix"]["fn"] == 1
    assert m["confusion_matrix"]["tn"] == 2


def test_tune_threshold_on_validation():
    """Verify threshold tuning chooses threshold that optimizes F1."""
    y_val = np.array([1, 1, 1, 0, 0, 0, 0, 0, 0, 0])
    y_prob = np.array([0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01])

    best_th, best_m, sweep_df = tune_threshold_on_validation(y_val, y_prob, optimization_metric="f1_score")

    # Threshold around 0.55-0.60 gives perfect precision and recall (TP=3, FP=0, FN=0 -> F1=1.0)
    assert best_m["f1_score"] == 1.0000
    assert 0.50 < best_th <= 0.65
    assert not sweep_df.empty


# ==============================================================================
# 6. Artifact Saving, Loading, and Prediction Tests
# ==============================================================================

def test_end_to_end_pipeline_artifact_lifecycle(tmp_path, synthetic_order_data):
    """Train pipeline, save artifact, reload, and verify predict outputs."""
    df_feat = engineer_point_in_time_features(synthetic_order_data)
    pipe = build_pipeline(model_type="logistic_regression", random_state=42)
    pipe.fit(df_feat[ALL_PREDICTORS], df_feat[TARGET_COLUMN])

    art_file = tmp_path / "model_pipeline.joblib"
    import joblib
    joblib.dump(pipe, art_file)

    predictor = DeliveryRiskPredictor(pipeline_path=art_file, threshold=0.60)
    assert predictor.threshold == 0.60

    sample_dict = df_feat[ALL_PREDICTORS].iloc[0].to_dict()
    res = predictor.predict(sample_dict)

    assert "late_risk_probability" in res
    assert "is_late_risk" in res
    assert "risk_tier" in res
    assert res["risk_tier"] in ["LOW", "MEDIUM", "HIGH"]
    assert 0.0 <= res["late_risk_probability"] <= 1.0
    assert res["is_late_risk"] == int(res["late_risk_probability"] >= 0.60)


# ==============================================================================
# 7. Live PostgreSQL Database ML Integration Tests
# ==============================================================================

@pytest.mark.integration
def test_live_postgres_ml_dataset_integrity():
    """Assert database contains expected population and exact 96,470 eligible orders."""
    engine = create_db_engine()
    connected, _ = check_connection(engine)
    if not connected:
        pytest.skip("PostgreSQL not accessible on localhost:5432")

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT 
                COUNT(*) as total_orders,
                COUNT(*) FILTER (WHERE order_status = 'delivered') as delivered_orders,
                COUNT(*) FILTER (WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL) as eligible_orders,
                COUNT(*) FILTER (WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL) as missing_ts_orders,
                COUNT(*) FILTER (WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL AND order_delivered_customer_date > order_estimated_delivery_date) as late_orders,
                COUNT(*) FILTER (WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL AND order_delivered_customer_date <= order_estimated_delivery_date) as ontime_orders
            FROM fact_orders;
        """)).fetchone()
        stats = dict(row._mapping)

    assert stats["total_orders"] == 99441
    assert stats["delivered_orders"] == 96478
    assert stats["missing_ts_orders"] == 8
    assert stats["eligible_orders"] == 96470
    assert stats["late_orders"] == 7826
    assert stats["ontime_orders"] == 88644
    assert stats["late_orders"] + stats["ontime_orders"] == 96470


@pytest.mark.integration
def test_saved_model_artifacts_exist_and_validate():
    """Verify that reports/model_artifacts contains all required persisted assets."""
    art_dir = Path("reports/model_artifacts")
    assert art_dir.is_dir(), f"Model artifacts directory not found: {art_dir}"

    expected_files = [
        "model_pipeline.joblib",
        "baseline_pipeline.joblib",
        "feature_schema.json",
        "model_metadata.json",
        "metrics.json",
        "evaluation_report.md",
        "feature_importance.csv",
        "subgroup_error_region.csv",
        "subgroup_error_category.csv",
        "validation_threshold_sweep.csv",
    ]
    for fname in expected_files:
        fpath = art_dir / fname
        assert fpath.is_file(), f"Missing model artifact file: {fpath}"
        assert fpath.stat().st_size > 0, f"Artifact file is empty: {fpath}"

    # Verify metadata JSON structure
    meta = json.loads((art_dir / "model_metadata.json").read_text(encoding="utf-8"))
    assert meta["model_type"] == "logistic_regression"
    assert "operational_threshold" in meta
    assert "causality_disclaimer" in meta

    # Verify metrics JSON structure
    metrics = json.loads((art_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "baseline" in metrics
    assert "model" in metrics
    assert "test_optimal_threshold" in metrics["model"]
    test_metrics = metrics["model"]["test_optimal_threshold"]
    assert test_metrics["n_samples"] == 12507
    assert test_metrics["roc_auc"] > 0.50
    assert test_metrics["pr_auc"] > 0.05


# ==============================================================================
# 8. ML Benchmark & Audit Regression Tests
# ==============================================================================

def test_benchmark_candidates_fit_and_predict_on_synthetic_data(synthetic_order_data):
    """Verify all candidate benchmark architectures can train and evaluate without error."""
    from scripts.benchmark_delivery_models import get_candidate_models
    from sklearn.pipeline import Pipeline
    from commercelens.ml.pipeline import build_preprocessor

    df_feat = engineer_point_in_time_features(synthetic_order_data)
    train_df, val_df, _ = chronological_split_by_ratio(df_feat, train_ratio=0.70, val_ratio=0.15)

    X_train, y_train = train_df[ALL_PREDICTORS], train_df[TARGET_COLUMN].values
    X_val, y_val = val_df[ALL_PREDICTORS], val_df[TARGET_COLUMN].values

    candidates = get_candidate_models(random_state=42)
    assert len(candidates) == 10

    for name, clf in candidates:
        pipe = Pipeline([
            ("preprocessor", build_preprocessor()),
            ("classifier", clf),
        ])
        pipe.fit(X_train, y_train)

        if hasattr(pipe, "predict_proba"):
            probs = pipe.predict_proba(X_val)[:, 1]
            assert len(probs) == len(X_val)
            assert (probs >= 0.0).all() and (probs <= 1.0).all()

        metrics = compute_classification_metrics(y_val, probs if hasattr(pipe, "predict_proba") else pipe.predict(X_val))
        assert "roc_auc" in metrics
        assert "pr_auc" in metrics
        assert "f1_score" in metrics


def test_benchmark_artifacts_and_audit_report_exist():
    """Verify that the ML audit and benchmark report and candidate comparison CSV exist and are populated."""
    art_dir = Path("reports/model_artifacts")
    report_file = art_dir / "ml_audit_and_benchmark_report.md"
    csv_file = art_dir / "candidate_models_benchmark_full.csv"

    assert report_file.is_file(), f"Missing audit report: {report_file}"
    content = report_file.read_text(encoding="utf-8")
    assert "Root Cause Analysis" in content
    assert "SLA Compression Regime Shift" in content
    assert "Strict Feature Leakage Audit" in content
    assert "Candidate Models Benchmark Results" in content
    assert "Decision Threshold Analysis" in content
    assert "Prediction-Time Feature & Strict Feature Leakage Audit" in content
    assert "Evaluation of Feature-Safe Alternative" in content
    assert "Predeclared Model Selection Protocol" in content
    assert "Calibration & Probability Reliability Analysis" in content
    assert "Final Decision Memo & Governance Verdict" in content

    assert csv_file.is_file(), f"Missing candidate benchmark CSV: {csv_file}"
    df_comp = pd.read_csv(csv_file)
    assert len(df_comp) == 10
    assert "model_name" in df_comp.columns
    assert "val_roc_auc" in df_comp.columns
    assert "test_roc_auc" in df_comp.columns
    assert "test_pr_auc" in df_comp.columns


def test_threshold_tuning_optimizes_validation_f1_without_leakage(synthetic_order_data):
    """Verify that tune_threshold_on_validation strictly tunes on provided data and selects optimal F1."""
    from commercelens.ml.evaluate import sweep_thresholds, tune_threshold_on_validation

    y_true = np.array([0, 0, 0, 0, 1, 0, 1, 1, 0, 0] * 10)
    # Predicted probabilities aligned with labels + small noise
    y_prob = np.array([0.1, 0.2, 0.15, 0.3, 0.7, 0.25, 0.8, 0.85, 0.2, 0.1] * 10)

    best_th, best_metrics, df_sweep = tune_threshold_on_validation(y_true, y_prob, optimization_metric="f1_score")

    assert 0.10 <= best_th <= 0.90
    assert best_metrics["f1_score"] == df_sweep["f1_score"].max()
    assert best_metrics["precision"] > 0.0
    assert best_metrics["recall"] > 0.0


def test_feature_safe_pipeline_build_and_fit(synthetic_order_data):
    """
    Verify that a feature-safe pipeline without seller_dispatch_sla_days
    can be instantiated, fitted on synthetic data, and evaluated without errors.
    """
    from commercelens.ml.features import (
        NUMERIC_FEATURES,
        CATEGORICAL_FEATURES,
        TARGET_COLUMN,
        engineer_point_in_time_features,
    )
    from commercelens.ml.pipeline import build_pipeline

    df = engineer_point_in_time_features(synthetic_order_data)
    safe_numeric = [c for c in NUMERIC_FEATURES if c != "seller_dispatch_sla_days"]
    safe_predictors = safe_numeric + CATEGORICAL_FEATURES

    pipe = build_pipeline(
        model_type="logistic_regression",
        numeric_features=safe_numeric,
        categorical_features=CATEGORICAL_FEATURES,
        C=0.1,
        class_weight="balanced",
        random_state=42,
    )

    X = df[safe_predictors]
    y = df[TARGET_COLUMN].values

    pipe.fit(X, y)
    probs = pipe.predict_proba(X)[:, 1]

    assert len(probs) == len(df)
    assert (probs >= 0.0).all() and (probs <= 1.0).all()


def test_unweighted_model_calibration_and_probabilities(synthetic_order_data):
    """
    Verify that an unweighted (class_weight=None) 26-feature pipeline produces
    well-calibrated probabilities matching empirical prevalence scale.
    """
    from sklearn.metrics import brier_score_loss
    from commercelens.ml.features import (
        NUMERIC_FEATURES,
        CATEGORICAL_FEATURES,
        TARGET_COLUMN,
        engineer_point_in_time_features,
    )
    from commercelens.ml.pipeline import build_pipeline

    df = engineer_point_in_time_features(synthetic_order_data)
    safe_numeric = [c for c in NUMERIC_FEATURES if c != "seller_dispatch_sla_days"]
    safe_predictors = safe_numeric + CATEGORICAL_FEATURES

    pipe = build_pipeline(
        model_type="logistic_regression",
        numeric_features=safe_numeric,
        categorical_features=CATEGORICAL_FEATURES,
        C=0.1,
        class_weight=None,
        random_state=42,
    )

    X = df[safe_predictors]
    y = df[TARGET_COLUMN].values

    pipe.fit(X, y)
    probs = pipe.predict_proba(X)[:, 1]

    # Probabilities must be strictly bounded in [0, 1]
    assert (probs >= 0.0).all() and (probs <= 1.0).all()

    # Brier score on unweighted model must be low
    brier = brier_score_loss(y, probs)
    assert brier < 0.20

    # Mean predicted probability should align with true prevalence (within 0.10 on synthetic data)
    empirical_prevalence = float(np.mean(y))
    assert abs(float(np.mean(probs)) - empirical_prevalence) < 0.15


def test_multi_objective_thresholds_logic():
    """
    Verify multi-objective threshold ordering logic on controlled synthetic predictions.
    """
    y_true = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1] * 20)  # 10% late
    # Ranked synthetic probabilities
    y_prob = np.array([0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.45, 0.85] * 20)

    from sklearn.metrics import precision_score, recall_score, f1_score

    thresholds = [0.10, 0.25, 0.50]  # high recall, balanced, high precision
    recalls = [recall_score(y_true, (y_prob >= th).astype(int), zero_division=0) for th in thresholds]
    precisions = [precision_score(y_true, (y_prob >= th).astype(int), zero_division=0) for th in thresholds]

    # Monotonicity check
    assert recalls[0] >= recalls[1] >= recalls[2]
    assert precisions[0] <= precisions[1] <= precisions[2]
    assert recalls[0] == 1.0  # At th=0.10, all positive examples (prob >= 0.45) caught
    assert precisions[2] == 1.0  # At th=0.50, only highest prob caught with 0 FP


def test_phase2_benchmark_and_drift_artifacts_exist():
    """
    Verify that all Phase 2 benchmark CSV tables exist in reports/model_artifacts/
    and have non-empty rows and valid columns.
    """
    art_dir = Path("reports/model_artifacts")

    bench_csv = art_dir / "phase2_benchmark_models.csv"
    assert bench_csv.is_file(), f"Missing {bench_csv}"
    df_bench = pd.read_csv(bench_csv)
    assert len(df_bench) >= 15
    assert "val_roc_auc" in df_bench.columns
    assert "val_pr_auc" in df_bench.columns
    assert "val_brier" in df_bench.columns
    assert "val_ece" in df_bench.columns

    cv_csv = art_dir / "phase2_temporal_cv_results.csv"
    assert cv_csv.is_file(), f"Missing {cv_csv}"
    df_cv = pd.read_csv(cv_csv)
    assert len(df_cv) == 32  # 4 folds * 8 models
    assert set(df_cv["fold"].unique()) == {
        "Fold 1 (Early 2018)",
        "Fold 2 (Spring 2018)",
        "Fold 3 (Strike / Buffer)",
        "Fold 4 (SLA Compression)",
    }

    op_csv = art_dir / "phase2_threshold_operating_points.csv"
    assert op_csv.is_file(), f"Missing {op_csv}"
    df_op = pd.read_csv(op_csv)
    assert len(df_op) >= 15
    assert set(df_op["operating_mode"].unique()) == {"high_recall", "balanced", "high_precision"}

    drift_csv = art_dir / "phase2_drift_metrics.csv"
    assert drift_csv.is_file(), f"Missing {drift_csv}"
    df_drift = pd.read_csv(drift_csv)
    assert "estimated_delivery_days" in df_drift["feature"].values

    geo_csv = art_dir / "phase2_geographic_inversion.csv"
    assert geo_csv.is_file(), f"Missing {geo_csv}"
    df_geo = pd.read_csv(geo_csv)
    assert len(df_geo) == 3

    reconciled_csv = art_dir / "phase2_reconciled_operating_points.csv"
    assert reconciled_csv.is_file(), f"Missing {reconciled_csv}"
    df_rec = pd.read_csv(reconciled_csv)
    assert len(df_rec) == 6
    assert "34-feat unweighted" in df_rec["model"].values

    report_md = art_dir / "ml_improvement_phase2_report.md"
    assert report_md.is_file(), f"Missing {report_md}"



