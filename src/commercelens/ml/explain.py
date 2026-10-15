"""
CommerceLens AI — Model Explainability & Subgroup Error Analysis
================================================================
Provides coefficient interpretations, odds ratios, permutation importance,
and subgroup error diagnostics across geographic regions and categories.
Includes explicit scientific governance distinguishing predictive correlation
from causal intervention.
"""

from typing import Dict, List, Any
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.pipeline import Pipeline


CAUSALITY_DISCLAIMER: str = (
    "STATISTICAL GOVERNANCE NOTICE: Feature contributions and odds ratios quantify "
    "observational statistical associations with late delivery under historical Correios/Olist "
    "operating conditions. They DO NOT establish causal mechanisms. For example, high freight ratios "
    "or extended SLA promises reflect inter-state transit difficulty and postal logistics pricing, "
    "not that charging more freight causes parcels to arrive late. Stakeholders must treat model outputs "
    "as risk indicators for operational monitoring, not guarantees or causal levers."
)


def get_feature_names_from_preprocessor(preprocessor) -> List[str]:
    """Extracts output feature names from the fitted ColumnTransformer."""
    feature_names = []
    for name, transformer, cols in preprocessor.transformers_:
        if name == "remainder" and transformer == "drop":
            continue
        if hasattr(transformer, "named_steps"):
            last_step = transformer.named_steps[list(transformer.named_steps.keys())[-1]]
            if hasattr(last_step, "get_feature_names_out"):
                names = last_step.get_feature_names_out(cols)
                feature_names.extend(names)
            else:
                feature_names.extend(cols)
        elif hasattr(transformer, "get_feature_names_out"):
            names = transformer.get_feature_names_out(cols)
            feature_names.extend(names)
        else:
            feature_names.extend(cols)
    return [str(f) for f in feature_names]


def get_logistic_regression_importance(
    pipeline: Pipeline,
) -> pd.DataFrame:
    """
    Extracts standardized coefficients and odds ratios from fitted Logistic Regression.
    Odds ratio > 1.0 indicates increased late-delivery odds per standard-deviation increase.
    """
    preprocessor = pipeline.named_steps["preprocessor"]
    model = pipeline.named_steps["classifier"]

    if not hasattr(model, "coef_"):
        raise ValueError("Model in pipeline does not expose coef_ (not a linear model).")

    feature_names = get_feature_names_from_preprocessor(preprocessor)
    coefs = model.coef_[0]

    df_coef = pd.DataFrame({
        "feature": feature_names,
        "coefficient": np.round(coefs, 4),
        "abs_coefficient": np.round(np.abs(coefs), 4),
        "odds_ratio": np.round(np.exp(coefs), 4),
        "risk_direction": np.where(coefs > 0, "Increases Late Risk", "Decreases Late Risk"),
    }).sort_values("abs_coefficient", ascending=False).reset_index(drop=True)

    return df_coef


def get_tree_feature_importance(
    pipeline: Pipeline,
) -> pd.DataFrame:
    """
    Extracts Mean Decrease in Impurity (MDI) feature importances from a tree-based model.
    """
    preprocessor = pipeline.named_steps["preprocessor"]
    model = pipeline.named_steps["classifier"]

    if not hasattr(model, "feature_importances_"):
        raise ValueError("Model in pipeline does not expose feature_importances_.")

    feature_names = get_feature_names_from_preprocessor(preprocessor)
    importances = model.feature_importances_

    df_imp = pd.DataFrame({
        "feature": feature_names,
        "importance": np.round(importances, 4),
    }).sort_values("importance", ascending=False).reset_index(drop=True)

    return df_imp


def compute_permutation_importance(
    pipeline: Pipeline,
    X_eval: pd.DataFrame,
    y_eval: np.ndarray | pd.Series,
    n_repeats: int = 5,
    random_state: int = 42,
    scoring: str = "average_precision",
) -> pd.DataFrame:
    """
    Computes permutation importance on holdout validation data.
    Quantifies degradation in PR-AUC when each raw predictor is randomly shuffled.
    """
    perm = permutation_importance(
        pipeline,
        X_eval,
        y_eval,
        n_repeats=n_repeats,
        random_state=random_state,
        scoring=scoring,
        n_jobs=-1,
    )

    df_perm = pd.DataFrame({
        "feature": X_eval.columns,
        "importance_mean": np.round(perm.importances_mean, 4),
        "importance_std": np.round(perm.importances_std, 4),
    }).sort_values("importance_mean", ascending=False).reset_index(drop=True)

    return df_perm


def perform_subgroup_error_analysis(
    df_eval: pd.DataFrame,
    subgroup_col: str,
    y_true_col: str = "is_late",
    y_prob_col: str = "late_probability",
    threshold: float = 0.5,
    min_samples: int = 30,
) -> pd.DataFrame:
    """
    Performs disaggregated error analysis across geographic regions, states, or categories.
    Reveals model performance disparities across subpopulations.
    """
    eval_df = df_eval.copy()
    eval_df["y_pred"] = (eval_df[y_prob_col] >= threshold).astype(int)

    results = []
    for grp, sub in eval_df.groupby(subgroup_col):
        n = len(sub)
        if n < min_samples:
            continue
        actual_late = int(sub[y_true_col].sum())
        pred_late = int(sub["y_pred"].sum())
        tp = int(((sub[y_true_col] == 1) & (sub["y_pred"] == 1)).sum())
        fp = int(((sub[y_true_col] == 0) & (sub["y_pred"] == 1)).sum())
        fn = int(((sub[y_true_col] == 1) & (sub["y_pred"] == 0)).sum())
        tn = int(((sub[y_true_col] == 0) & (sub["y_pred"] == 0)).sum())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        results.append({
            subgroup_col: grp,
            "sample_size": n,
            "actual_late_count": actual_late,
            "actual_late_rate_pct": round(actual_late / n * 100, 2),
            "predicted_late_rate_pct": round(pred_late / n * 100, 2),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        })

    return pd.DataFrame(results).sort_values("sample_size", ascending=False).reset_index(drop=True)
