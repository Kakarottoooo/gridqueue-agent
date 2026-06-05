from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.db import TABLES, init_database, reset_database, table_counts


def test_database_schema_can_be_initialized(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    reset_database(db_path)

    counts = table_counts(db_path)

    assert set(counts) == set(TABLES)
    assert all(count == 0 for count in counts.values())


def test_database_schema_initialization_is_thread_safe(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: init_database(db_path), range(16)))

    counts = table_counts(db_path)

    assert set(counts) == set(TABLES)
    assert all(count == 0 for count in counts.values())
