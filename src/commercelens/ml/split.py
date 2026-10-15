"""
CommerceLens AI — Chronological Data Splitting & Validation Module
===================================================================
Provides strict chronological splitting of e-commerce orders based on
purchase timestamp, preventing temporal leakage and forward-looking bias.
"""

from typing import Tuple, Dict, Any
import pandas as pd


def chronological_split_by_date(
    df: pd.DataFrame,
    time_col: str = "order_purchase_timestamp",
    val_cutoff: str = "2018-05-01",
    test_cutoff: str = "2018-07-01",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Partitions the dataset chronologically using clean calendar cutoffs:
      - Train: purchase < val_cutoff (Inception through April 30, 2018)
      - Validation: val_cutoff <= purchase < test_cutoff (May 1 through June 30, 2018)
      - Test: purchase >= test_cutoff (July 1 through August 29, 2018)
      
    Asserts zero order overlap and strict temporal ordering.
    """
    df_sorted = df.sort_values(time_col).copy()
    df_sorted[time_col] = pd.to_datetime(df_sorted[time_col])
    val_dt = pd.to_datetime(val_cutoff)
    test_dt = pd.to_datetime(test_cutoff)

    train_df = df_sorted[df_sorted[time_col] < val_dt].copy()
    val_df = df_sorted[(df_sorted[time_col] >= val_dt) & (df_sorted[time_col] < test_dt)].copy()
    test_df = df_sorted[df_sorted[time_col] >= test_dt].copy()

    # Enforce data hygiene constraints
    _validate_split_integrity(train_df, val_df, test_df, time_col)

    return train_df, val_df, test_df


def chronological_split_by_ratio(
    df: pd.DataFrame,
    time_col: str = "order_purchase_timestamp",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Partitions the dataset chronologically by row proportion (e.g., 70% / 15% / 15%).
    Sorts ascending by purchase timestamp and slices indices.
    """
    df_sorted = df.sort_values(time_col).copy()
    df_sorted[time_col] = pd.to_datetime(df_sorted[time_col])

    n = len(df_sorted)
    idx_train = int(n * train_ratio)
    idx_val = int(n * (train_ratio + val_ratio))

    train_df = df_sorted.iloc[:idx_train].copy()
    val_df = df_sorted.iloc[idx_train:idx_val].copy()
    test_df = df_sorted.iloc[idx_val:].copy()

    _validate_split_integrity(train_df, val_df, test_df, time_col)

    return train_df, val_df, test_df


def _validate_split_integrity(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    time_col: str,
) -> None:
    """Verifies that split partitions are non-empty, disjoint, and temporally ordered."""
    if train_df.empty or val_df.empty or test_df.empty:
        raise ValueError(
            f"Split error: one or more partitions are empty! (Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)})"
        )

    # Check order_id disjointness if present
    if "order_id" in train_df.columns:
        train_ids = set(train_df["order_id"])
        val_ids = set(val_df["order_id"])
        test_ids = set(test_df["order_id"])

        overlap_tv = train_ids.intersection(val_ids)
        overlap_tt = train_ids.intersection(test_ids)
        overlap_vt = val_ids.intersection(test_ids)

        if overlap_tv or overlap_tt or overlap_vt:
            raise ValueError(
                f"Data Leakage Violation: Overlapping order IDs found across chronological splits! "
                f"(Train-Val: {len(overlap_tv)}, Train-Test: {len(overlap_tt)}, Val-Test: {len(overlap_vt)})"
            )

    # Check temporal monotonicity
    if train_df[time_col].max() > val_df[time_col].min():
        raise ValueError(
            f"Temporal Leakage Violation: Training max timestamp ({train_df[time_col].max()}) "
            f"exceeds validation min timestamp ({val_df[time_col].min()})."
        )

    if val_df[time_col].max() > test_df[time_col].min():
        raise ValueError(
            f"Temporal Leakage Violation: Validation max timestamp ({val_df[time_col].max()}) "
            f"exceeds test min timestamp ({test_df[time_col].min()})."
        )


def get_split_summary_stats(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    time_col: str = "order_purchase_timestamp",
    target_col: str = "is_late",
) -> Dict[str, Any]:
    """Generates structured metadata documenting the chronological splits."""
    total_n = len(train_df) + len(val_df) + len(test_df)
    return {
        "total_observations": total_n,
        "train": {
            "n": len(train_df),
            "pct": round(len(train_df) / total_n * 100, 2),
            "start": str(train_df[time_col].min()),
            "end": str(train_df[time_col].max()),
            "late_count": int(train_df[target_col].sum()) if target_col in train_df else None,
            "late_rate_pct": round(train_df[target_col].mean() * 100, 2) if target_col in train_df else None,
        },
        "validation": {
            "n": len(val_df),
            "pct": round(len(val_df) / total_n * 100, 2),
            "start": str(val_df[time_col].min()),
            "end": str(val_df[time_col].max()),
            "late_count": int(val_df[target_col].sum()) if target_col in val_df else None,
            "late_rate_pct": round(val_df[target_col].mean() * 100, 2) if target_col in val_df else None,
        },
        "test": {
            "n": len(test_df),
            "pct": round(len(test_df) / total_n * 100, 2),
            "start": str(test_df[time_col].min()),
            "end": str(test_df[time_col].max()),
            "late_count": int(test_df[target_col].sum()) if target_col in test_df else None,
            "late_rate_pct": round(test_df[target_col].mean() * 100, 2) if target_col in test_df else None,
        },
    }
