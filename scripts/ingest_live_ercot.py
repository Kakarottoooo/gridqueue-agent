from __future__ import annotations

import argparse

from app.services.ingestion import ingest_manual_file


ERCOT_GIS_URL = "https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er"


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ERCOT GIS data from a local manually downloaded file.")
    parser.add_argument("path", nargs="?", help="Path to a local ERCOT GIS CSV/XLSX file under data/raw or elsewhere.")
    args = parser.parse_args()
    if not args.path:
        print("Manual ERCOT GIS ingestion fallback")
        print(f"1. Download the GIS Report from: {ERCOT_GIS_URL}")
        print("2. Place the file in data/raw/")
        print("3. Run: python scripts/ingest_live_ercot.py data/raw/<downloaded-file.xlsx>")
        return
    result = ingest_manual_file(
        args.path,
        market="ERCOT",
        source_name="ERCOT GIS Report manual file",
        source_url=ERCOT_GIS_URL,
        source_type="manual_ercot_gis",
        ingestion_mode="manual_ercot",
    )
    print(result)


if __name__ == "__main__":
    main()

