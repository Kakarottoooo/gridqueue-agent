from __future__ import annotations

import argparse

from app.services.ingestion import ingest_manual_file


LBNL_URL = "https://emp.lbl.gov/queues"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest LBNL Queued Up data from a local manually downloaded file.")
    parser.add_argument("path", nargs="?", help="Path to a local LBNL CSV/XLSX file under data/raw or elsewhere.")
    args = parser.parse_args()
    if not args.path:
        print("Manual LBNL Queued Up ingestion fallback")
        print(f"1. Download Queued Up data from: {LBNL_URL}")
        print("2. Place the file in data/raw/")
        print("3. Run: python scripts/ingest_lbnl.py data/raw/<downloaded-file.xlsx>")
        return
    result = ingest_manual_file(
        args.path,
        market="LBNL",
        source_name="LBNL Queued Up manual file",
        source_url=LBNL_URL,
        source_type="manual_lbnl",
        ingestion_mode="manual_lbnl",
    )
    print(result)


if __name__ == "__main__":
    main()

