from __future__ import annotations

from app.db import TABLES, reset_database, table_counts


def test_database_schema_can_be_initialized(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    reset_database(db_path)

    counts = table_counts(db_path)

    assert set(counts) == set(TABLES)
    assert all(count == 0 for count in counts.values())

