"""
Master Phase 1 Data Ingestion and Quality Audit Pipeline.

Coordinates:
1. File discovery and presence validation.
2. Safe loading and metadata profiling.
3. Quality audit (missing values, duplicates, candidate keys, relationships, business rules).
4. Safe data cleaning and derived dataset export.
5. Multi-format reporting (JSON, CSV, Markdown).
"""

from pathlib import Path
import json
from typing import Any, Dict

from commercelens.data.ingest import discover_raw_files, load_raw_dataset_inventory
from commercelens.data.audit import execute_comprehensive_audit
from commercelens.data.clean import clean_all_datasets, save_processed_datasets
from commercelens.data.report import generate_all_reports


def run_phase1_pipeline(
    data_raw_dir: Path,
    data_processed_dir: Path,
    reports_dir: Path,
) -> Dict[str, Any]:
    """
    Execute the Phase 1 Ingestion, Profiling and Quality Audit pipeline.
    
    If the 9 expected CSV files are missing or incomplete, stops immediately
    before processing, records the missing files manifest, and halts.
    """
    raw_path = Path(data_raw_dir).resolve()
    proc_path = Path(data_processed_dir).resolve()
    rep_path = Path(reports_dir).resolve()

    found_files, missing_files = discover_raw_files(raw_path)

    # In accordance with Step 1:4 - Stop before processing if dataset is missing or incomplete
    if missing_files:
        status_dir = rep_path / "data_quality"
        status_dir.mkdir(parents=True, exist_ok=True)
        status_payload = {
            "status": "HALTED_MISSING_RAW_DATA",
            "message": f"Pipeline halted before processing. {len(missing_files)} of 9 expected raw CSV files are missing.",
            "discovered_files_count": len(found_files),
            "missing_files_count": len(missing_files),
            "missing_files": missing_files,
            "raw_directory": str(raw_path),
        }
        with open(status_dir / "pipeline_status.json", "w", encoding="utf-8") as f:
            json.dump(status_payload, f, indent=2)

        return status_payload

    # Step 2: Ingest all datasets safely
    tables, inventory, _ = load_raw_dataset_inventory(raw_path, require_all=True)

    # Step 3: Run comprehensive quality audit
    audit_results = execute_comprehensive_audit(tables)

    # Step 4: Produce reports
    report_paths = generate_all_reports(inventory, audit_results, rep_path)

    # Step 5: Clean datasets safely and save derived tables to data/processed/
    cleaned_tables, cleaning_summary = clean_all_datasets(tables)
    saved_proc_files = save_processed_datasets(cleaned_tables, proc_path)

    status_payload = {
        "status": "COMPLETED_SUCCESSFULLY",
        "discovered_files_count": len(found_files),
        "missing_files_count": 0,
        "inventory": [inv.model_dump() for inv in inventory],
        "cleaning_summary": cleaning_summary,
        "saved_processed_files": {k: str(v) for k, v in saved_proc_files.items()},
        "report_paths": {k: str(v) for k, v in report_paths.items()},
    }

    status_file = rep_path / "data_quality" / "pipeline_status.json"
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_payload, f, indent=2)

    return status_payload
