from __future__ import annotations

import argparse
from pathlib import Path

from app.services.real_validation.ercot_gis import manual_ercot_download_instructions, profile_ercot_gis_workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile real ERCOT GIS XLSX workbook(s).")
    parser.add_argument("files", nargs="*", help="Workbook path(s). Defaults to data/raw/real/ercot/gis/*.xlsx.")
    parser.add_argument("--snapshot-date", help="Snapshot date for a single workbook, YYYY-MM-DD.")
    args = parser.parse_args()
    files = [Path(item) for item in args.files] or sorted(Path("data/raw/real/ercot/gis").glob("*.xlsx"))
    if not files:
        print("No ERCOT GIS XLSX files found.")
        for step in manual_ercot_download_instructions():
            print(f"- {step}")
        return
    for file_path in files:
        result = profile_ercot_gis_workbook(file_path, snapshot_date=args.snapshot_date if len(files) == 1 else None)
        print(result["profile_markdown_path"])


if __name__ == "__main__":
    main()
