from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.diffing import diff_snapshots
from app.services.entity_resolution import resolve_market
from app.services.flexibility import seed_flexibility_rules
from app.services.ingestion import run_fixture_pipeline
from app.services.watcher.digest import generate_monthly_digest, list_change_events
from app.services.watcher.queue_adapter import adapt_queue_diff
from app.services.watcher.regulatory_snapshot import capture_regulatory_snapshots
from app.services.watcher.sources import seed_watch_sources


def run_monthly_watcher(
    *,
    mode: str = "fixture",
    period_start: str | date,
    period_end: str | date,
    market: str = "ERCOT",
    from_snapshot_id: str | None = None,
    to_snapshot_id: str | None = None,
    top_n: int = 10,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    if mode == "fixture" and not _has_snapshots(market, db_path):
        run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    seed_watch_sources(db_path)
    snapshot_pair = _snapshot_pair(market, from_snapshot_id, to_snapshot_id, db_path)
    resolve_market(market, db_path)
    diff_snapshots(market, snapshot_pair["from_snapshot_id"], snapshot_pair["to_snapshot_id"], db_path)
    queue_result = adapt_queue_diff(
        market=market,
        from_snapshot_id=snapshot_pair["from_snapshot_id"],
        to_snapshot_id=snapshot_pair["to_snapshot_id"],
        db_path=db_path,
    )
    regulatory_result = capture_regulatory_snapshots(mode=mode, fixture_variant="current", db_path=db_path)
    digest = generate_monthly_digest(period_start=period_start, period_end=period_end, top_n=top_n, db_path=db_path)
    change_events = list_change_events(db_path=db_path)
    return {
        "status": "completed",
        "mode": mode,
        "market": market,
        "from_snapshot_id": snapshot_pair["from_snapshot_id"],
        "to_snapshot_id": snapshot_pair["to_snapshot_id"],
        "queue_adapter": queue_result,
        "regulatory_snapshot": {
            "source_snapshot_count": regulatory_result["source_snapshot_count"],
            "change_event_count": regulatory_result["change_event_count"],
        },
        "digest": digest,
        "change_event_count": len(change_events),
    }


def _has_snapshots(market: str, db_path: str | Path | None) -> bool:
    with connect(db_path) as con:
        count = con.execute("SELECT COUNT(*) FROM snapshots WHERE market = ?", [market]).fetchone()[0]
    return bool(count)


def _snapshot_pair(
    market: str,
    from_snapshot_id: str | None,
    to_snapshot_id: str | None,
    db_path: str | Path | None,
) -> dict[str, str]:
    if from_snapshot_id and to_snapshot_id:
        return {"from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id}
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT snapshot_id
            FROM snapshots
            WHERE market = ?
            ORDER BY snapshot_date DESC, snapshot_id DESC
            LIMIT 2
            """,
            [market],
        ).fetchall()
    if len(rows) < 2:
        raise ValueError(f"At least two snapshots are required for watcher queue diff in {market}.")
    return {"from_snapshot_id": rows[1][0], "to_snapshot_id": rows[0][0]}
