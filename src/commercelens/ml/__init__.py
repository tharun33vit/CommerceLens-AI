"""
CommerceLens AI — Machine Learning Module
=========================================
Implements delivery-risk prediction pipelines, point-in-time feature engineering,
chronological splitting, imbalanced evaluation, threshold selection, and explainability.
"""

from commercelens.ml.features import (
    ALL_PREDICTORS,
    FORBIDDEN_LEAKAGE_COLUMNS,
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    TARGET_COLUMN,
    engineer_point_in_time_features,
    extract_raw_features_from_db,
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
    CAUSALITY_DISCLAIMER,
    get_logistic_regression_importance,
    get_tree_feature_importance,
    compute_permutation_importance,
    perform_subgroup_error_analysis,
)
from commercelens.ml.predict import (
    DeliveryRiskPredictor,
    load_delivery_predictor,
)

__all__ = [
    "ALL_PREDICTORS",
    "FORBIDDEN_LEAKAGE_COLUMNS",
    "NUMERIC_FEATURES",
    "CATEGORICAL_FEATURES",
    "TARGET_COLUMN",
    "engineer_point_in_time_features",
    "extract_raw_features_from_db",
    "haversine_distance",
    "validate_no_leakage",
    "chronological_split_by_date",
    "chronological_split_by_ratio",
    "get_split_summary_stats",
    "build_model",
    "build_pipeline",
    "build_preprocessor",
    "compute_classification_metrics",
    "sweep_thresholds",
    "tune_threshold_on_validation",
    "CAUSALITY_DISCLAIMER",
    "get_logistic_regression_importance",
    "get_tree_feature_importance",
    "compute_permutation_importance",
    "perform_subgroup_error_analysis",
    "DeliveryRiskPredictor",
    "load_delivery_predictor",
]
