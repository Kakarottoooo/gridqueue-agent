from __future__ import annotations

from app.db import table_counts
from app.services.ingestion import run_fixture_pipeline


def main() -> None:
    result = run_fixture_pipeline(reset=True)
    print("Ingested synthetic fixtures")
    print(result)
    print(table_counts())


if __name__ == "__main__":
    main()

