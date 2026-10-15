"""
CommerceLens AI — Model Evaluation & Decision Threshold Selection
===================================================================
Computes imbalanced-classification evaluation metrics (PR-AUC, ROC-AUC,
Precision, Recall, F1, Confusion Matrix) and selects operational decision
thresholds on validation data.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def compute_classification_metrics(
    y_true: np.ndarray | pd.Series,
    y_prob: np.ndarray,
    threshold: float = 0.5,
) -> Dict[str, Any]:
    """
    Computes comprehensive evaluation metrics for late-delivery risk prediction.
    Prioritizes PR-AUC and minority-class Precision/Recall over raw Accuracy.
    """
    y_true_arr = np.asarray(y_true, dtype=int)
    y_prob_arr = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob_arr >= threshold).astype(int)

    # Base rate & support
    n_total = len(y_true_arr)
    n_positive = int(np.sum(y_true_arr))
    prevalence = float(n_positive / n_total) if n_total > 0 else 0.0

    # Discrimination metrics
    # ROC-AUC requires at least one positive and one negative observation
    if len(np.unique(y_true_arr)) > 1 and len(np.unique(y_prob_arr)) > 1:
        roc_auc = float(roc_auc_score(y_true_arr, y_prob_arr))
        pr_auc = float(average_precision_score(y_true_arr, y_prob_arr))
    else:
        roc_auc = 0.5
        pr_auc = prevalence

    # Calibration metric
    brier = float(brier_score_loss(y_true_arr, y_prob_arr))

    # Confusion matrix
    tn, fp, fn, tp = confusion_matrix(y_true_arr, y_pred, labels=[0, 1]).ravel()
    prec = float(precision_score(y_true_arr, y_pred, zero_division=0))
    rec = float(recall_score(y_true_arr, y_pred, zero_division=0))
    f1 = float(f1_score(y_true_arr, y_pred, zero_division=0))
    acc = float((tp + tn) / n_total) if n_total > 0 else 0.0
    specificity = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0

    return {
        "n_samples": n_total,
        "n_late": n_positive,
        "prevalence_late": round(prevalence, 4),
        "threshold": round(threshold, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "brier_score": round(brier, 4),
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4),
        "specificity": round(specificity, 4),
        "confusion_matrix": {
            "tp": int(tp),
            "fp": int(fp),
            "fn": int(fn),
            "tn": int(tn),
        },
    }


def sweep_thresholds(
    y_true: np.ndarray | pd.Series,
    y_prob: np.ndarray,
    threshold_step: float = 0.05,
) -> pd.DataFrame:
    """
    Sweeps probability thresholds across validation data to analyze trade-offs
    between false positives and missed deliveries.
    """
    thresholds = np.arange(0.10, 0.91, threshold_step)
    rows: List[Dict[str, Any]] = []

    for th in thresholds:
        m = compute_classification_metrics(y_true, y_prob, threshold=float(th))
        cm = m["confusion_matrix"]
        rows.append({
            "threshold": m["threshold"],
            "precision": m["precision"],
            "recall": m["recall"],
            "f1_score": m["f1_score"],
            "accuracy": m["accuracy"],
            "tp": cm["tp"],
            "fp": cm["fp"],
            "fn": cm["fn"],
            "tn": cm["tn"],
        })

    return pd.DataFrame(rows)


def tune_threshold_on_validation(
    y_val: np.ndarray | pd.Series,
    val_probs: np.ndarray,
    optimization_metric: str = "f1_score",
) -> Tuple[float, Dict[str, Any], pd.DataFrame]:
    """
    Finds the optimal operational probability threshold using validation data.
    Never uses test set for threshold selection.
    """
    df_sweep = sweep_thresholds(y_val, val_probs, threshold_step=0.01)

    if optimization_metric == "f1_score":
        best_row = df_sweep.loc[df_sweep["f1_score"].idxmax()]
        best_th = float(best_row["threshold"])
    elif optimization_metric == "balanced_recall":
        # Target recall around ~60-70% while maintaining precision
        subset = df_sweep[df_sweep["recall"] >= 0.60]
        if not subset.empty:
            best_row = subset.loc[subset["precision"].idxmax()]
            best_th = float(best_row["threshold"])
        else:
            best_th = 0.50
    else:
        best_th = 0.50

    best_metrics = compute_classification_metrics(y_val, val_probs, threshold=best_th)
    return best_th, best_metrics, df_sweep
