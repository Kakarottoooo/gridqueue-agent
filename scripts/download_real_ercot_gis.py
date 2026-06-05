from __future__ import annotations

from app.services.real_validation.ercot_gis import download_latest_ercot_gis_reports, manual_ercot_download_instructions


def main() -> None:
    result = download_latest_ercot_gis_reports(count=2)
    print(result)
    if result.get("status") != "downloaded":
        print("Manual ERCOT GIS download required:")
        for step in manual_ercot_download_instructions():
            print(f"- {step}")


if __name__ == "__main__":
    main()
