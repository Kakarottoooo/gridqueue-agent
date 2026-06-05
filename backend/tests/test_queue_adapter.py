from __future__ import annotations

from app.services.ingestion import run_fixture_pipeline
from app.services.watcher import adapt_queue_diff


def test_queue_adapter_preserves_ambiguity_without_hard_alert(tmp_path) -> None:
    db_path = tmp_path / "queue_adapter.duckdb"
    run_fixture_pipeline(db_path, reset=True)

    result = adapt_queue_diff(
        market="ERCOT",
        from_snapshot_id="snap_ercot_2026_01_31",
        to_snapshot_id="snap_ercot_2026_02_28",
        db_path=db_path,
    )

    ambiguous = [event for event in result["change_events"] if event["event_type"] == "ambiguous_match"]
    assert ambiguous
    assert all(event["is_ambiguous"] for event in ambiguous)
    assert all(not event["is_hard_alert"] for event in ambiguous)
    assert not any(event["event_type"] == "unchanged" for event in result["change_events"])
