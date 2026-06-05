from __future__ import annotations

import argparse

from app.services.real_validation.entity_resolution_audit import build_ercot_entity_resolution_audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an entity-resolution audit CSV for a real ERCOT snapshot pair.")
    parser.add_argument("--from-snapshot-id", required=True)
    parser.add_argument("--to-snapshot-id", required=True)
    args = parser.parse_args()
    print(build_ercot_entity_resolution_audit(from_snapshot_id=args.from_snapshot_id, to_snapshot_id=args.to_snapshot_id))


if __name__ == "__main__":
    main()
