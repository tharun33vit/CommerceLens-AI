"""
CommerceLens AI — Machine Learning Pipeline & Model Architecture
================================================================
Defines scikit-learn Pipelines, ColumnTransformers, and model architectures.
Ensures imputation, scaling, and encoding parameters are fitted strictly
on training data.
"""

from typing import List, Literal
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from commercelens.ml.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def build_preprocessor(
    numeric_features: List[str] | None = None,
    categorical_features: List[str] | None = None,
) -> ColumnTransformer:
    """
    Builds a ColumnTransformer that imputes and scales numeric features,
    and imputes and one-hot encodes categorical features.
    """
    num_cols = numeric_features or NUMERIC_FEATURES
    cat_cols = categorical_features or CATEGORICAL_FEATURES

    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    cat_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    return ColumnTransformer(
        transformers=[
            ("num", num_pipeline, num_cols),
            ("cat", cat_pipeline, cat_cols),
        ],
        remainder="drop",
    )


def build_model(
    model_type: Literal["dummy", "logistic_regression", "random_forest", "hist_gradient_boosting"] = "logistic_regression",
    class_weight: str | dict | None = "balanced",
    random_state: int = 42,
    **kwargs,
) -> BaseEstimator:
    """
    Factory function for baseline and supervised classification models.
    """
    if model_type == "dummy":
        return DummyClassifier(strategy="most_frequent")

    elif model_type == "logistic_regression":
        c_param = kwargs.get("C", 0.1)
        max_iter = kwargs.get("max_iter", 1000)
        return LogisticRegression(
            C=c_param,
            max_iter=max_iter,
            class_weight=class_weight,
            random_state=random_state,
        )

    elif model_type == "random_forest":
        n_estimators = kwargs.get("n_estimators", 100)
        max_depth = kwargs.get("max_depth", 8)
        min_samples_leaf = kwargs.get("min_samples_leaf", 30)
        return RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            class_weight=class_weight,
            random_state=random_state,
            n_jobs=-1,
        )

    elif model_type == "hist_gradient_boosting":
        learning_rate = kwargs.get("learning_rate", 0.05)
        max_iter = kwargs.get("max_iter", 100)
        max_depth = kwargs.get("max_depth", 6)
        min_samples_leaf = kwargs.get("min_samples_leaf", 30)
        return HistGradientBoostingClassifier(
            learning_rate=learning_rate,
            max_iter=max_iter,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            class_weight=class_weight,
            random_state=random_state,
        )

    else:
        raise ValueError(f"Unsupported model_type: '{model_type}'. Choose from dummy, logistic_regression, random_forest, hist_gradient_boosting.")


def build_pipeline(
    model_type: Literal["dummy", "logistic_regression", "random_forest", "hist_gradient_boosting"] = "logistic_regression",
    numeric_features: List[str] | None = None,
    categorical_features: List[str] | None = None,
    class_weight: str | dict | None = "balanced",
    random_state: int = 42,
    **kwargs,
) -> Pipeline:
    """
    Creates an end-to-end scikit-learn Pipeline linking the preprocessor and the classifier.
    """
    preprocessor = build_preprocessor(numeric_features, categorical_features)
    classifier = build_model(
        model_type=model_type,
        class_weight=class_weight,
        random_state=random_state,
        **kwargs,
    )

    return Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", classifier),
    ])
