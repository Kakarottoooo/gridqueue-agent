from __future__ import annotations

import argparse
from calendar import monthrange
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.watcher import run_monthly_watcher  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local GridQueue monthly watcher.")
    parser.add_argument("--mode", choices=["fixture", "manual", "live"], default="fixture")
    parser.add_argument("--period", required=True, help="Period in YYYY-MM format.")
    parser.add_argument("--market", default="ERCOT")
    parser.add_argument("--from-snapshot-id", default=None)
    parser.add_argument("--to-snapshot-id", default=None)
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()
    year, month = [int(part) for part in args.period.split("-", maxsplit=1)]
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"
    result = run_monthly_watcher(
        mode=args.mode,
        period_start=period_start,
        period_end=period_end,
        market=args.market,
        from_snapshot_id=args.from_snapshot_id,
        to_snapshot_id=args.to_snapshot_id,
        top_n=args.top_n,
    )
    print(json.dumps({"status": result["status"], "digest_id": result["digest"]["digest_id"], "markdown_path": result["digest"]["markdown_path"]}, indent=2))


if __name__ == "__main__":
    main()
