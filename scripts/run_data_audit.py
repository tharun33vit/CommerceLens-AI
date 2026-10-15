"""
Execution Script for Phase 1 Data Ingestion, Profiling and Quality Audit.

Usage:
    python scripts/run_data_audit.py
"""

import sys
from pathlib import Path

# Ensure src is on sys.path
repo_root = Path(__file__).resolve().parent.parent
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from commercelens.data.pipeline import run_phase1_pipeline


def main() -> int:
    raw_dir = repo_root / "data" / "raw"
    proc_dir = repo_root / "data" / "processed"
    rep_dir = repo_root / "reports"

    print("==================================================================")
    print("CommerceLens AI — Phase 1: Ingestion & Quality Audit Pipeline")
    print("==================================================================")
    print(f"Target Raw Directory:       {raw_dir}")
    print(f"Target Processed Directory: {proc_dir}")
    print(f"Target Reports Directory:   {rep_dir / 'data_quality'}")
    print("------------------------------------------------------------------")

    result = run_phase1_pipeline(
        data_raw_dir=raw_dir,
        data_processed_dir=proc_dir,
        reports_dir=rep_dir,
    )

    status = result.get("status")
    if status == "HALTED_MISSING_RAW_DATA":
        print("\n[!] PIPELINE HALTED BEFORE PROCESSING:")
        print(f"    {result.get('message')}")
        print("\nMissing files required in data/raw/:")
        for f in result.get("missing_files", []):
            print(f"    - {f}")
        print("\nPlease download the Olist Brazilian E-Commerce dataset from Kaggle:")
        print("https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce")
        print("and place the 9 CSV files into data/raw/ before re-running.")
        return 1

    print("\n[SUCCESS] Pipeline executed successfully.")
    print(f"Discovered Tables: {result.get('discovered_files_count')}")
    print("Generated Reports:")
    for name, path in result.get("report_paths", {}).items():
        print(f"    - {name}: {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
