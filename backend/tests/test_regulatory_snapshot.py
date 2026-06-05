from __future__ import annotations

from app.db import connect, reset_database
from app.services.watcher import capture_regulatory_snapshots, seed_watch_sources


def test_regulatory_snapshot_emits_source_changes_and_parse_failures(tmp_path) -> None:
    db_path = tmp_path / "reg_snapshot.duckdb"
    reset_database(db_path)
    seed_watch_sources(db_path)

    result = capture_regulatory_snapshots(mode="fixture", db_path=db_path)

    assert result["source_snapshot_count"] >= 6
    event_types = {event["event_type"] for event in result["change_events"]}
    assert "rule_source_changed" in event_types
    assert "source_parse_failed" in event_types
    assert any(event["source_url"] for event in result["change_events"])


def test_regulatory_final_language_requires_review_not_silent_status_update(tmp_path) -> None:
    db_path = tmp_path / "reg_review.duckdb"
    reset_database(db_path)
    seed_watch_sources(db_path)

    capture_regulatory_snapshots(mode="fixture", db_path=db_path)
    changed = capture_regulatory_snapshots(mode="fixture", fixture_variant="changed", db_path=db_path)

    assert any(event["event_type"] == "rule_needs_review" for event in changed["change_events"])
    with connect(db_path) as con:
        status = con.execute(
            "SELECT status FROM iso_flexibility_rules WHERE rule_id = 'rule_ferc_rm26_4_anopr'"
        ).fetchone()[0]
    assert status == "pending"
