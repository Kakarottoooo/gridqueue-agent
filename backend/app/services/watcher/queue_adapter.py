from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.diffing import diff_snapshots
from app.services.watcher.events import insert_change_event


SKIPPED_QUEUE_EVENT_TYPES = {"unchanged"}


def adapt_queue_diff(
    *,
    market: str,
    from_snapshot_id: str,
    to_snapshot_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        existing = con.execute(
            "SELECT COUNT(*) FROM diff_events WHERE market = ? AND from_snapshot_id = ? AND to_snapshot_id = ?",
            [market, from_snapshot_id, to_snapshot_id],
        ).fetchone()[0]
    if not existing:
        diff_snapshots(market, from_snapshot_id, to_snapshot_id, db_path)

    created: list[dict[str, Any]] = []
    with connect(db_path) as con:
        con.execute(
            """
            DELETE FROM change_events
            WHERE event_domain = 'queue' AND market = ? AND from_snapshot_id = ? AND to_snapshot_id = ?
            """,
            [market, from_snapshot_id, to_snapshot_id],
        )
        rows = con.execute(
            """
            SELECT event_id, market, from_snapshot_id, to_snapshot_id, entity_id, event_type, severity,
                   confidence, before_record_id, after_record_id, changed_fields_json, explanation, created_at
            FROM diff_events
            WHERE market = ? AND from_snapshot_id = ? AND to_snapshot_id = ?
            ORDER BY event_type, entity_id
            """,
            [market, from_snapshot_id, to_snapshot_id],
        ).fetchall()
        source_url = _snapshot_source_url(con, to_snapshot_id)
        for row in rows:
            event_type = row[5]
            if event_type in SKIPPED_QUEUE_EVENT_TYPES:
                continue
            before_record = _record(con, row[8])
            after_record = _record(con, row[9])
            changed_fields = _json(row[10])
            is_ambiguous = event_type == "ambiguous_match"
            entity_name = (
                after_record.get("project_name")
                or before_record.get("project_name")
                or row[4]
            )
            created.append(
                insert_change_event(
                    con,
                    event_domain="queue",
                    event_type=event_type,
                    market=market,
                    entity_or_provision=entity_name,
                    entity_id=row[4],
                    from_snapshot_id=row[2],
                    to_snapshot_id=row[3],
                    source_url=source_url,
                    before_json={**before_record, "changed_fields_json": changed_fields},
                    after_json={**after_record, "changed_fields_json": changed_fields},
                    confidence=float(row[7]),
                    is_ambiguous=is_ambiguous,
                    is_hard_alert_value=False if is_ambiguous else None,
                    explanation=row[11],
                    citation_ids=[item for item in (row[2], row[3]) if item],
                )
            )
    return {
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "adapted_event_count": len(created),
        "change_events": created,
    }


def _snapshot_source_url(con: Any, snapshot_id: str) -> str | None:
    row = con.execute(
        """
        SELECT s.source_url
        FROM snapshots sn
        JOIN sources s ON s.source_id = sn.source_id
        WHERE sn.snapshot_id = ?
        """,
        [snapshot_id],
    ).fetchone()
    return row[0] if row else None


def _record(con: Any, record_id: str | None) -> dict[str, Any]:
    if not record_id:
        return {}
    row = con.execute(
        """
        SELECT record_id, snapshot_id, market, queue_id, project_name, county, state,
               point_of_interconnection, normalized_fuel_type, capacity_mw, normalized_status, target_cod
        FROM normalized_project_records
        WHERE record_id = ?
        """,
        [record_id],
    ).fetchone()
    if not row:
        return {}
    return {
        "record_id": row[0],
        "snapshot_id": row[1],
        "market": row[2],
        "queue_id": row[3],
        "project_name": row[4],
        "county": row[5],
        "state": row[6],
        "point_of_interconnection": row[7],
        "normalized_fuel_type": row[8],
        "capacity_mw": row[9],
        "normalized_status": row[10],
        "target_cod": row[11].isoformat() if hasattr(row[11], "isoformat") else row[11],
    }


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
