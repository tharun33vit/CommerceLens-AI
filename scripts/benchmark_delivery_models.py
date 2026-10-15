"""
CommerceLens AI — ML Delivery-Risk Benchmark Script
===================================================
Conducts an empirical benchmark of candidate tabular classification models
(Majority Dummy, Logistic Regression variants, Random Forest variants,
Extra Trees, and HistGradientBoosting variants) using strict chronological
splitting and validation-based decision threshold selection.

Usage:
    python scripts/benchmark_delivery_models.py [--output-dir reports/model_artifacts]
"""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

# Add src to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from commercelens.analytics.db import create_db_engine, check_connection
from commercelens.ml.features import (
    ALL_PREDICTORS,
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    TARGET_COLUMN,
    engineer_point_in_time_features,
    extract_raw_features_from_db,
    validate_no_leakage,
)
from commercelens.ml.split import (
    chronological_split_by_date,
    get_split_summary_stats,
)
from commercelens.ml.pipeline import build_preprocessor
from commercelens.ml.evaluate import (
    compute_classification_metrics,
    tune_threshold_on_validation,
    sweep_thresholds,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("CommerceLens-ML-Benchmark")


def get_candidate_models(random_state: int = 42) -> List[Tuple[str, Any]]:
    """Returns the list of candidate model architectures and configurations for benchmarking."""
    return [
        (
            "Majority Baseline (Dummy)",
            DummyClassifier(strategy="most_frequent"),
        ),
        (
            "Logistic Regression (C=0.01, balanced)",
            LogisticRegression(C=0.01, class_weight="balanced", max_iter=1000, random_state=random_state),
        ),
        (
            "Logistic Regression (C=0.1, balanced) [Existing]",
            LogisticRegression(C=0.1, class_weight="balanced", max_iter=1000, random_state=random_state),
        ),
        (
            "Logistic Regression (C=1.0, balanced)",
            LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, random_state=random_state),
        ),
        (
            "Random Forest (d=8, n=100, balanced)",
            RandomForestClassifier(
                n_estimators=100,
                max_depth=8,
                min_samples_leaf=30,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            ),
        ),
        (
            "Random Forest (d=12, n=150, balanced)",
            RandomForestClassifier(
                n_estimators=150,
                max_depth=12,
                min_samples_leaf=20,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            ),
        ),
        (
            "Extra Trees (d=8, n=100, balanced)",
            ExtraTreesClassifier(
                n_estimators=100,
                max_depth=8,
                min_samples_leaf=30,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            ),
        ),
        (
            "HistGradientBoosting (d=4, lr=0.05, balanced)",
            HistGradientBoostingClassifier(
                max_depth=4,
                learning_rate=0.05,
                max_iter=100,
                min_samples_leaf=30,
                class_weight="balanced",
                random_state=random_state,
            ),
        ),
        (
            "HistGradientBoosting (d=6, lr=0.05, balanced)",
            HistGradientBoostingClassifier(
                max_depth=6,
                learning_rate=0.05,
                max_iter=100,
                min_samples_leaf=30,
                class_weight="balanced",
                random_state=random_state,
            ),
        ),
        (
            "HistGradientBoosting (d=6, lr=0.03, l2=1.0, balanced)",
            HistGradientBoostingClassifier(
                max_depth=6,
                learning_rate=0.03,
                max_iter=150,
                l2_regularization=1.0,
                min_samples_leaf=40,
                class_weight="balanced",
                random_state=random_state,
            ),
        ),
    ]


def run_benchmark(
    output_dir: Path | str = "reports/model_artifacts",
    val_cutoff: str = "2018-05-01",
    test_cutoff: str = "2018-07-01",
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Executes the comprehensive ML benchmark and outputs summary tables and metrics.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("================================================================================")
    logger.info("COMMERCELENS AI — ML IMPROVEMENT: BENCHMARK CANDIDATE MODELS")
    logger.info("================================================================================")

    # 1. Database Extraction
    engine = create_db_engine()
    connected, err = check_connection(engine)
    if not connected:
        raise ConnectionError(f"PostgreSQL connection failed: {err}")

    logger.info("Extracting feature dataset from PostgreSQL...")
    raw_df = extract_raw_features_from_db(engine)
    logger.info(f"Extracted {len(raw_df):,} orders.")

    # 2. Point-in-time features with training-fitted categories
    hist_cats = raw_df[raw_df["order_purchase_timestamp"] < val_cutoff]["primary_category"]
    top_categories = hist_cats.value_counts().head(15).index.tolist()
    df = engineer_point_in_time_features(raw_df, top_categories=top_categories)
    validate_no_leakage(ALL_PREDICTORS)

    # 3. Chronological splitting
    train_df, val_df, test_df = chronological_split_by_date(
        df,
        time_col="order_purchase_timestamp",
        val_cutoff=val_cutoff,
        test_cutoff=test_cutoff,
    )
    split_stats = get_split_summary_stats(train_df, val_df, test_df)
    logger.info(f"Split sizes: Train={len(train_df):,}, Val={len(val_df):,}, Test={len(test_df):,}")

    X_train, y_train = train_df[ALL_PREDICTORS], train_df[TARGET_COLUMN].values
    X_val, y_val = val_df[ALL_PREDICTORS], val_df[TARGET_COLUMN].values
    X_test, y_test = test_df[ALL_PREDICTORS], test_df[TARGET_COLUMN].values

    # 4. Benchmark loop
    candidates = get_candidate_models(random_state=random_state)
    comparison_rows: List[Dict[str, Any]] = []

    logger.info(f"Beginning benchmark of {len(candidates)} candidate architectures...")

    for name, clf in candidates:
        logger.info(f"--- Training: {name} ---")
        t0 = time.time()
        pipe = Pipeline([
            ("preprocessor", build_preprocessor()),
            ("classifier", clf),
        ])
        pipe.fit(X_train, y_train)
        fit_time = time.time() - t0

        val_probs = pipe.predict_proba(X_val)[:, 1] if hasattr(pipe, "predict_proba") else pipe.predict(X_val).astype(float)
        test_probs = pipe.predict_proba(X_test)[:, 1] if hasattr(pipe, "predict_proba") else pipe.predict(X_test).astype(float)

        # Validation tuning (F1-optimal)
        opt_th, m_val_opt, _ = tune_threshold_on_validation(y_val, val_probs, optimization_metric="f1_score")
        m_val_def = compute_classification_metrics(y_val, val_probs, threshold=0.50)

        # Final evaluation on untouched test set
        m_test_def = compute_classification_metrics(y_test, test_probs, threshold=0.50)
        m_test_opt = compute_classification_metrics(y_test, test_probs, threshold=opt_th)

        logger.info(
            f"  Val ROC-AUC: {m_val_def['roc_auc']:.4f} | Val PR-AUC: {m_val_def['pr_auc']:.4f} | "
            f"Opt-Th: {opt_th:.2f} (Val F1: {m_val_opt['f1_score']:.4f})"
        )
        logger.info(
            f"  Test ROC-AUC: {m_test_def['roc_auc']:.4f} | Test PR-AUC: {m_test_def['pr_auc']:.4f} | "
            f"Test F1: {m_test_opt['f1_score']:.4f} (Prec: {m_test_opt['precision']:.4f}, Rec: {m_test_opt['recall']:.4f})"
        )

        comparison_rows.append({
            "model_name": name,
            "fit_time_seconds": round(fit_time, 2),
            "val_roc_auc": m_val_def["roc_auc"],
            "val_pr_auc": m_val_def["pr_auc"],
            "val_brier_score": m_val_def["brier_score"],
            "val_opt_threshold": round(opt_th, 2),
            "val_opt_precision": m_val_opt["precision"],
            "val_opt_recall": m_val_opt["recall"],
            "val_opt_f1": m_val_opt["f1_score"],
            "test_roc_auc": m_test_def["roc_auc"],
            "test_pr_auc": m_test_def["pr_auc"],
            "test_brier_score": m_test_def["brier_score"],
            "test_def_f1": m_test_def["f1_score"],
            "test_opt_precision": m_test_opt["precision"],
            "test_opt_recall": m_test_opt["recall"],
            "test_opt_f1": m_test_opt["f1_score"],
            "test_tp": m_test_opt["confusion_matrix"]["tp"],
            "test_fp": m_test_opt["confusion_matrix"]["fp"],
            "test_fn": m_test_opt["confusion_matrix"]["fn"],
            "test_tn": m_test_opt["confusion_matrix"]["tn"],
        })

    df_comp = pd.DataFrame(comparison_rows)

    # 5. Persist benchmark results
    csv_path = out_path / "candidate_models_benchmark_full.csv"
    df_comp.to_csv(csv_path, index=False)
    logger.info(f"Persisted benchmark comparison table to {csv_path}")

    json_path = out_path / "candidate_models_benchmark_summary.json"
    summary_payload = {
        "benchmark_timestamp_utc": datetime.utcnow().isoformat(),
        "split_summary": split_stats,
        "results": comparison_rows,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)
    logger.info(f"Persisted benchmark metadata JSON to {json_path}")

    return df_comp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CommerceLens AI ML Benchmark Runner")
    parser.add_argument("--output-dir", default="reports/model_artifacts", help="Output directory for benchmark artifacts")
    args = parser.parse_args()

    run_benchmark(output_dir=args.output_dir)
