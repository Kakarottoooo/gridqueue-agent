from __future__ import annotations

from pathlib import Path

from app.services.watcher import run_monthly_watcher


def test_watcher_digest_contains_traces_caveat_and_suppressed_events(tmp_path) -> None:
    db_path = tmp_path / "digest.duckdb"

    result = run_monthly_watcher(
        mode="fixture",
        period_start="2026-05-01",
        period_end="2026-05-31",
        top_n=5,
        db_path=db_path,
    )
    digest = result["digest"]

    sections = [
        *digest["top_queue_changes"],
        *digest["top_regulatory_changes"],
        *digest["flexibility_rule_watch"],
        *digest["suppressed_ambiguous"],
        *digest["parse_failures"],
    ]
    assert sections
    assert all(row["change_event_id"] for row in sections)
    assert all(row["source_url"] or row["source_trace"] for row in sections)
    assert digest["suppressed_ambiguous"]
    assert digest["parse_failures"]
    assert "public-data monitoring artifact" in digest["caveats"][0]
    assert Path(digest["markdown_path"]).exists()
