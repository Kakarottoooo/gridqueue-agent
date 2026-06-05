from __future__ import annotations

import argparse

from app.services.real_validation.ercot_gis import ingest_ercot_gis_workbook, manual_ercot_download_instructions


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one real ERCOT GIS workbook.")
    parser.add_argument("--file", required=False, help="Path to ERCOT GIS XLSX.")
    parser.add_argument("--snapshot-date", required=False, help="Snapshot date YYYY-MM-DD.")
    args = parser.parse_args()
    if not args.file or not args.snapshot_date:
        print("Manual ERCOT GIS ingestion requires --file and --snapshot-date.")
        for step in manual_ercot_download_instructions():
            print(f"- {step}")
        return
    print(ingest_ercot_gis_workbook(args.file, snapshot_date=args.snapshot_date))


if __name__ == "__main__":
    main()
