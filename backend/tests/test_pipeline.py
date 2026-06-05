from __future__ import annotations

from app.db import connect, table_counts
from app.services.brief_generation import generate_brief
from app.services.ingestion import run_fixture_pipeline
from app.services.metrics import compute_metric_rollup


def test_fixture_pipeline_populates_core_tables(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    counts = table_counts(db_path)

    assert counts["snapshots"] == 2
    assert counts["raw_project_records"] == 29
    assert counts["normalized_project_records"] == 29
    assert counts["project_entity_links"] == 29
    assert counts["diff_events"] >= 12
    assert counts["citations"] == 29


def test_changed_queue_id_links_to_same_entity(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT r.queue_id, l.entity_id, l.match_method, l.match_score
            FROM project_entity_links l
            JOIN normalized_project_records r ON r.record_id = l.record_id
            WHERE r.queue_id IN ('Q-1002', 'Q-2002')
            ORDER BY r.queue_id
            """
        ).fetchall()

    assert len(rows) == 2
    assert rows[0][1] == rows[1][1]
    assert rows[1][2] == "high_confidence_match"
    assert rows[1][3] >= 0.76


def test_diff_avoids_false_new_for_renamed_and_reclassified_projects(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    with connect(db_path) as con:
        events = con.execute(
            """
            SELECT event_type, changed_fields_json, explanation
            FROM diff_events
            WHERE from_snapshot_id = 'snap_ercot_2026_01_31'
              AND to_snapshot_id = 'snap_ercot_2026_02_28'
            """
        ).fetchall()

    serialized = "\n".join(str(row) for row in events)
    assert "Lone Star Solar Project" in serialized
    assert "name_changed" in serialized
    assert "fuel_type_changed" in serialized
    assert "Sunfield" not in _new_project_payload(events)


def test_ambiguous_matches_are_flagged_not_forced(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    with connect(db_path) as con:
        ambiguous_count = con.execute(
            "SELECT COUNT(*) FROM project_entity_links WHERE is_ambiguous = TRUE"
        ).fetchone()[0]
        diff_count = con.execute(
            "SELECT COUNT(*) FROM diff_events WHERE event_type = 'ambiguous_match'"
        ).fetchone()[0]

    assert ambiguous_count == 2
    assert diff_count == 2


def test_metrics_roll_up_and_abstain_when_samples_are_too_small(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    rolled = compute_metric_rollup(market="ERCOT", county="Comanche", fuel_type="Battery", min_sample_n=2, db_path=db_path)
    insufficient = compute_metric_rollup(market="ERCOT", county="Comanche", fuel_type="Battery", min_sample_n=100, db_path=db_path)

    assert rolled["fallback_level"] == "market_fuel"
    assert rolled["sample_n"] >= 2
    assert rolled["withdrawal_rate"] is not None
    assert insufficient["confidence"] == "Insufficient"
    assert insufficient["completion_rate"] is None


def test_brief_contains_citations_caveats_sample_size_and_large_load_abstention(tmp_path) -> None:
    db_path = tmp_path / "gridqueue.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    brief = generate_brief(
        market="ERCOT",
        project_type="Battery",
        county="Reeves",
        capacity_mw=100,
        target_cod_year=2028,
        question="How does this affect a data center large load?",
        min_sample_n=2,
        db_path=db_path,
    )

    assert brief["citations"]
    assert brief["historical_proxy"]["sample_n"] >= 2
    assert "formal interconnection study" in "\n".join(brief["caveats_and_abstentions"])
    assert brief["large_load_context"] is not None
    assert "generation-resource records" in brief["large_load_context"]["summary"]


def _new_project_payload(events: list[tuple[str, str, str]]) -> str:
    return "\n".join(str(row) for row in events if row[0] == "new_project")

