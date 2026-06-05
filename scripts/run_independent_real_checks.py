from __future__ import annotations

import argparse

from app.services.real_validation.independent_checks import run_independent_real_checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent direct-XLSX checks for real data outputs.")
    parser.add_argument("--ercot-from-file")
    parser.add_argument("--ercot-to-file")
    parser.add_argument("--lbnl-file")
    args = parser.parse_args()
    print(
        run_independent_real_checks(
            ercot_from_file=args.ercot_from_file,
            ercot_to_file=args.ercot_to_file,
            lbnl_file=args.lbnl_file,
        )
    )


if __name__ == "__main__":
    main()
