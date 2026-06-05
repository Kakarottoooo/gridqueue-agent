from __future__ import annotations

import argparse
from pathlib import Path

from app.services.real_validation.lbnl import manual_lbnl_download_instructions, run_lbnl_reproduction


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LBNL Queued Up real workbook reproduction checks.")
    parser.add_argument("--file", default="data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx")
    args = parser.parse_args()
    path = Path(args.file)
    if not path.exists():
        print(f"LBNL workbook not found: {path}")
        for step in manual_lbnl_download_instructions():
            print(f"- {step}")
        return
    print(run_lbnl_reproduction(path))


if __name__ == "__main__":
    main()
