"""
Data Ingestion and CSV Loading Module for CommerceLens AI.

Provides robust CSV discovery, encoding fallback, safe datetime parsing,
and metadata profiling for the Olist Brazilian E-Commerce dataset.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from commercelens.data.schema import (
    DATETIME_COLUMNS,
    EXPECTED_RAW_FILES,
    TableInventoryItem,
)


class RawDataMissingError(FileNotFoundError):
    """Raised when one or more required raw CSV files are missing."""
    def __init__(self, missing_files: List[str]):
        self.missing_files = missing_files
        message = (
            f"The following {len(missing_files)} expected raw dataset file(s) are missing:\n"
            + "\n".join(f"  - {f}" for f in missing_files)
            + "\nPlease download the Olist Brazilian E-Commerce dataset and place all CSV files in data/raw/."
        )
        super().__init__(message)


def discover_raw_files(data_raw_dir: Path) -> Tuple[Dict[str, Path], List[str]]:
    """
    Inspect the raw data directory for the 9 expected Olist CSV files.

    Args:
        data_raw_dir: Path to directory containing raw CSVs.

    Returns:
        Tuple of (found_files_dict, missing_files_list)
        found_files_dict: mapping of table_name -> absolute Path
        missing_files_list: list of expected filenames that were not found.
    """
    raw_path = Path(data_raw_dir).resolve()
    found: Dict[str, Path] = {}
    missing: List[str] = []

    for table_name, filename in EXPECTED_RAW_FILES.items():
        expected_file = raw_path / filename
        if expected_file.is_file() and expected_file.stat().st_size > 0:
            found[table_name] = expected_file
        else:
            missing.append(filename)

    return found, missing


def read_raw_csv(
    file_path: Path,
    table_name: Optional[str] = None,
    parse_dates: bool = True,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Safely load a raw CSV file into a pandas DataFrame without modifying the source.
    Tries UTF-8 first, then falls back to Latin-1 encoding for Brazilian Portuguese text.

    Args:
        file_path: Absolute Path to the CSV file.
        table_name: Optional identifier to look up known datetime columns.
        parse_dates: Whether to parse known datetime columns safely.

    Returns:
        Tuple of (df, parsed_datetime_columns)
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    # Read with UTF-8 first, fallback to Latin-1 / ISO-8859-1
    try:
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="latin-1", low_memory=False)

    parsed_datetimes: List[str] = []
    if parse_dates and table_name and table_name in DATETIME_COLUMNS:
        target_date_cols = DATETIME_COLUMNS[table_name]
        for col in target_date_cols:
            if col in df.columns:
                # Convert safely with coerce and format='mixed' to avoid unhandled crashes on invalid strings
                df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
                parsed_datetimes.append(col)

    return df, parsed_datetimes


def generate_table_inventory(
    table_name: str,
    file_path: Path,
    df: pd.DataFrame,
    parsed_datetimes: List[str],
) -> TableInventoryItem:
    """
    Compute metadata and type inventory for a loaded dataframe.
    """
    file_size = file_path.stat().st_size if file_path.exists() else 0
    inferred_types = {col: str(dtype) for col, dtype in df.dtypes.items()}

    return TableInventoryItem(
        table_name=table_name,
        file_name=file_path.name,
        file_size_bytes=file_size,
        row_count=len(df),
        column_count=len(df.columns),
        columns=list(df.columns),
        inferred_types=inferred_types,
        datetime_columns_parsed=parsed_datetimes,
    )


def load_raw_dataset_inventory(
    data_raw_dir: Path,
    require_all: bool = True,
) -> Tuple[Dict[str, pd.DataFrame], List[TableInventoryItem], List[str]]:
    """
    High-level loader for raw datasets.
    
    If require_all is True and any file is missing, stops immediately without
    loading partial data or fabricating sample records.

    Returns:
        Tuple of (loaded_dfs, inventory_items, missing_files)
    """
    found, missing = discover_raw_files(data_raw_dir)

    if missing and require_all:
        return {}, [], missing

    loaded_dfs: Dict[str, pd.DataFrame] = {}
    inventory_items: List[TableInventoryItem] = []

    for table_name, file_path in found.items():
        df, parsed_dt = read_raw_csv(file_path, table_name=table_name, parse_dates=True)
        inv = generate_table_inventory(table_name, file_path, df, parsed_dt)
        loaded_dfs[table_name] = df
        inventory_items.append(inv)

    return loaded_dfs, inventory_items, missing
