from __future__ import annotations

import argparse

from app.services.real_validation.ercot_gis import manual_ercot_download_instructions, run_real_ercot_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real ERCOT GIS pair validation.")
    parser.add_argument("--from-file", required=False)
    parser.add_argument("--from-snapshot-date", required=False)
    parser.add_argument("--to-file", required=False)
    parser.add_argument("--to-snapshot-date", required=False)
    args = parser.parse_args()
    if not all([args.from_file, args.from_snapshot_date, args.to_file, args.to_snapshot_date]):
        print("Real ERCOT pair run requires --from-file, --from-snapshot-date, --to-file, and --to-snapshot-date.")
        for step in manual_ercot_download_instructions():
            print(f"- {step}")
        return
    result = run_real_ercot_pair(
        from_file=args.from_file,
        from_snapshot_date=args.from_snapshot_date,
        to_file=args.to_file,
        to_snapshot_date=args.to_snapshot_date,
    )
    print(result)


if __name__ == "__main__":
    main()
