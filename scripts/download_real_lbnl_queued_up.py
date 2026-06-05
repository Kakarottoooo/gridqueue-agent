from __future__ import annotations

from app.services.real_validation.lbnl import download_lbnl_workbook, manual_lbnl_download_instructions


def main() -> None:
    result = download_lbnl_workbook()
    print(result)
    if result.get("status") != "downloaded":
        print("Manual LBNL download required:")
        for step in manual_lbnl_download_instructions():
            print(f"- {step}")


if __name__ == "__main__":
    main()
