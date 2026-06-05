from __future__ import annotations

from datetime import date

from app.db import connect, reset_database
from app.services.time_to_power.equipment_scope import generate_equipment_scope
from app.services.time_to_power.fixtures import seed_time_to_power_fixtures
from app.services.time_to_power.procurement_critical_path import DAYS_PER_MONTH, compute_procurement_critical_path


def test_critical_path_selects_binding_high_end_and_flags_stale_conflict(tmp_path) -> None:
    db_path = tmp_path / "critical_path.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)
    scope = generate_equipment_scope(project_type="AI data center load", peak_mw=300, interconnection_voltage_kv=345)

    result = compute_procurement_critical_path(
        scenario_id="scenario_test",
        equipment_scope=scope,
        current_date=date(2026, 6, 5),
        db_path=db_path,
    )

    assert result["binding_equipment_class"] == "Large Power Transformer"
    assert result["binding_lead_time_low_months"] == 36
    assert result["binding_lead_time_high_months"] == 60
    assert result["procurement_low_days"] == round(36 * DAYS_PER_MONTH, 2)
    assert result["procurement_high_days"] == round(60 * DAYS_PER_MONTH, 2)
    assert result["stale_flag"] is True
    assert result["conflict_flag"] is True
    assert result["unsupported_flag"] is False
    assert result["assumptions"]["days_per_month"] == DAYS_PER_MONTH
    assert all(row["lead_time_low_months"] < row["lead_time_high_months"] for row in result["lead_time_rows"])


def test_critical_path_missing_source_metadata_is_unsupported(tmp_path) -> None:
    db_path = tmp_path / "critical_path_missing_source.duckdb"
    reset_database(db_path)
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO lead_time_sources
            (lead_time_source_id, source_name, source_url, source_type, publication_date,
             retrieved_at, content_hash, notes, created_at)
            VALUES ('bad_src', 'Bad source', 'synthetic://bad-source', 'test', '2026-01-01',
                    CURRENT_TIMESTAMP, 'hash', 'test', CURRENT_TIMESTAMP)
            """
        )
        con.execute(
            """
            INSERT INTO equipment_lead_times
            (lead_time_id, equipment_class, voltage_or_rating_band, lead_time_low_months,
             lead_time_high_months, as_of_date, source_id, source_url, source_type, confidence,
             is_stale, stale_threshold_months, notes, created_at, updated_at)
            VALUES ('bad_row', 'Bad Equipment', 'test', 1, 2, '2026-01-01',
                    'bad_src', '', 'test', 'low', FALSE, 18, 'missing URL', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    scope = {"equipment_scope": [{"scope_item_id": "bad", "equipment_class": "Bad Equipment", "explanation": "test"}]}

    result = compute_procurement_critical_path(scenario_id="scenario_test", equipment_scope=scope, db_path=db_path)

    assert result["unsupported_flag"] is True
    assert result["procurement_low_days"] is None
    assert "No supported lead-time rows" in result["caveats"][1]
