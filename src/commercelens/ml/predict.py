"""
CommerceLens AI — Delivery Risk Prediction Utility & Serving Interface
========================================================================
Provides inference capabilities for predicting late-delivery risk on new orders
at checkout. Enforces strict input validation to prevent post-order leakage.
"""

from pathlib import Path
from typing import Any, Dict, List
import json
import joblib
import numpy as np
import pandas as pd

from commercelens.ml.features import (
    ALL_PREDICTORS,
    FORBIDDEN_LEAKAGE_COLUMNS,
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    engineer_point_in_time_features,
    validate_no_leakage,
)


class DeliveryRiskPredictor:
    """
    Inference interface for CommerceLens AI Delivery-Risk Prediction.
    Loads fitted pipeline artifacts, validates inputs, and predicts late delivery risk.
    """

    def __init__(
        self,
        pipeline_path: Path | str,
        metadata_path: Path | str | None = None,
        threshold: float | None = None,
    ):
        self.pipeline_path = Path(pipeline_path)
        if not self.pipeline_path.is_file():
            raise FileNotFoundError(f"Model artifact not found: {self.pipeline_path}")

        self.pipeline = joblib.load(self.pipeline_path)

        # Load metadata if present
        self.metadata = {}
        if metadata_path is not None and Path(metadata_path).is_file():
            with open(metadata_path, encoding="utf-8") as f:
                self.metadata = json.load(f)

        # Operational decision threshold
        if threshold is not None:
            self.threshold = float(threshold)
        elif "operational_threshold" in self.metadata:
            self.threshold = float(self.metadata["operational_threshold"])
        elif "f1_optimal_threshold" in self.metadata:
            self.threshold = float(self.metadata["f1_optimal_threshold"])
        else:
            self.threshold = 0.50

    def predict(self, data: Dict[str, Any] | pd.DataFrame) -> Dict[str, Any] | pd.DataFrame:
        """
        Predicts late-delivery risk for one or more orders.
        
        Args:
            data: Single order dictionary or DataFrame containing point-in-time features.
            
        Returns:
            Dictionary with prediction results for a single order, or DataFrame for multiple orders.
        """
        is_single = isinstance(data, dict)
        df_in = pd.DataFrame([data]) if is_single else data.copy()

        # 1. Enforce strict leakage rejection
        validate_no_leakage(df_in.columns)

        # 2. Check if derived features are present; if not, engineer them
        missing_preds = [c for c in ALL_PREDICTORS if c not in df_in.columns]
        if missing_preds:
            # Check if raw input columns exist to compute derived features
            raw_reqs = ["order_purchase_timestamp", "customer_state", "seller_state"]
            if all(r in df_in.columns for r in raw_reqs):
                top_cats = self.metadata.get("top_categories", None)
                df_engineered = engineer_point_in_time_features(df_in, top_categories=top_cats)
            else:
                raise ValueError(
                    f"Input is missing required predictors: {missing_preds}. "
                    f"Ensure input contains all predictors or raw order fields {raw_reqs}."
                )
        else:
            df_engineered = df_in

        # 3. Select predictor columns
        X = df_engineered[ALL_PREDICTORS]

        # 4. Predict probabilities
        if hasattr(self.pipeline, "predict_proba"):
            probs = self.pipeline.predict_proba(X)[:, 1]
        else:
            probs = self.pipeline.predict(X).astype(float)

        # 5. Classify risk tiers
        results_df = pd.DataFrame({
            "late_risk_probability": np.round(probs, 4),
            "is_late_risk": (probs >= self.threshold).astype(int),
            "risk_tier": pd.cut(
                probs,
                bins=[-1.0, 0.35, 0.65, 2.0],
                labels=["LOW", "MEDIUM", "HIGH"],
            ).astype(str),
            "decision_threshold": self.threshold,
        })

        if is_single:
            return results_df.iloc[0].to_dict()
        return results_df


def load_delivery_predictor(artifacts_dir: Path | str) -> DeliveryRiskPredictor:
    """Convenience loader from model artifacts directory."""
    art_path = Path(artifacts_dir)
    pipeline_file = art_path / "model_pipeline.joblib"
    meta_file = art_path / "model_metadata.json"

    if not pipeline_file.is_file():
        raise FileNotFoundError(f"Model pipeline not found in directory: {pipeline_file}")

    return DeliveryRiskPredictor(
        pipeline_path=pipeline_file,
        metadata_path=meta_file if meta_file.is_file() else None,
    )
