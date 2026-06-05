from __future__ import annotations

from datetime import date

from app.db import connect, reset_database
from app.services.procurement import list_lead_times, seed_lead_time_kb


def test_lead_time_kb_seeds_cited_range_with_staleness(tmp_path) -> None:
    db_path = tmp_path / "lead_time.duckdb"
    reset_database(db_path)

    first = seed_lead_time_kb(db_path)
    second = seed_lead_time_kb(db_path)
    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))

    assert first == second
    assert len(rows) == 1
    row = rows[0]
    assert row["equipment_class"] == "Large Power Transformer"
    assert row["lead_time_low_months"] == 36
    assert row["lead_time_high_months"] == 60
    assert row["lead_time_low_months"] != row["lead_time_high_months"]
    assert row["source_url"].startswith("https://www.energy.gov/")
    assert row["as_of_date"] == "2024-07-10"
    assert row["is_stale"] is True
    assert "not a procurement quote" in row["caveats"][0]


def test_lead_time_conflicts_are_flagged_without_collapsing_ranges(tmp_path) -> None:
    db_path = tmp_path / "lead_time_conflict.duckdb"
    reset_database(db_path)
    seed_lead_time_kb(db_path)

    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO lead_time_sources
            (lead_time_source_id, source_name, source_url, source_type, publication_date,
             retrieved_at, content_hash, notes, created_at)
            VALUES ('lead_src_test_conflict', 'Synthetic conflict source', 'synthetic://gridqueue-agent/test-lead-time-conflict',
                    'manual_fixture', '2026-01-01', CURRENT_TIMESTAMP, 'hash', 'Test-only conflict source.', CURRENT_TIMESTAMP)
            """
        )
        con.execute(
            """
            INSERT INTO equipment_lead_times
            (lead_time_id, equipment_class, voltage_or_rating_band, lead_time_low_months,
             lead_time_high_months, as_of_date, source_id, source_url, source_type, confidence,
             is_stale, stale_threshold_months, notes, created_at, updated_at)
            VALUES ('lead_test_conflict', 'Large Power Transformer', 'Transmission-class / high-voltage recovery transformer',
                    30, 48, '2026-01-01', 'lead_src_test_conflict',
                    'synthetic://gridqueue-agent/test-lead-time-conflict', 'manual_fixture', 'low',
                    FALSE, 18, 'Test-only conflicting range.', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )

    rows = list_lead_times(db_path=db_path, today=date(2026, 6, 5))

    assert len(rows) == 2
    assert all(row["has_conflict"] for row in rows)
    assert {(row["lead_time_low_months"], row["lead_time_high_months"]) for row in rows} == {(36.0, 60.0), (30.0, 48.0)}
