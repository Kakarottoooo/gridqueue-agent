from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.entity_resolution.resolver import capacity_within_tolerance
from app.services.utils import new_id, stable_json, utcnow


TARGET_COD_MOVE_DAYS = 90


def diff_adjacent_snapshots(market: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_database(db_path)
    with connect(db_path) as con:
        snapshot_ids = [
            row[0]
            for row in con.execute(
                "SELECT snapshot_id FROM snapshots WHERE market = ? ORDER BY snapshot_date, snapshot_id",
                [market],
            ).fetchall()
        ]
    results = []
    for before, after in zip(snapshot_ids, snapshot_ids[1:], strict=False):
        results.append(diff_snapshots(market, before, after, db_path))
    return results


def diff_snapshots(
    market: str,
    from_snapshot_id: str,
    to_snapshot_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        con.execute(
            "DELETE FROM diff_events WHERE market = ? AND from_snapshot_id = ? AND to_snapshot_id = ?",
            [market, from_snapshot_id, to_snapshot_id],
        )
        before_links = _links_for_snapshot(con, from_snapshot_id)
        after_links = _links_for_snapshot(con, to_snapshot_id)
        before_by_entity = {item["entity_id"]: item for item in before_links}
        after_by_entity = {item["entity_id"]: item for item in after_links}
        created = []

        for after in after_links:
            if after["is_ambiguous"]:
                created.append(
                    _insert_event(
                        con,
                        market=market,
                        from_snapshot_id=from_snapshot_id,
                        to_snapshot_id=to_snapshot_id,
                        entity_id=after["entity_id"],
                        event_type="ambiguous_match",
                        severity="warning",
                        confidence=after["match_score"],
                        before_record_id=None,
                        after_record_id=after["record"]["record_id"],
                        changed_fields={
                            "match_method": after["match_method"],
                            "match_features": after["match_features"],
                        },
                        explanation="The latest record resembles multiple prior projects; GridQueue did not force the match.",
                    )
                )
                continue
            if after["entity_id"] not in before_by_entity:
                created.append(
                    _insert_event(
                        con,
                        market=market,
                        from_snapshot_id=from_snapshot_id,
                        to_snapshot_id=to_snapshot_id,
                        entity_id=after["entity_id"],
                        event_type="new_project",
                        severity="info",
                        confidence=after["match_score"] if after["match_method"] != "new_entity" else 0.9,
                        before_record_id=None,
                        after_record_id=after["record"]["record_id"],
                        changed_fields={"after_project_name": after["record"]["project_name"]},
                        explanation="Project entity appears in the later snapshot without a non-ambiguous prior match.",
                    )
                )

        for entity_id, before in before_by_entity.items():
            after = after_by_entity.get(entity_id)
            if not after or after["is_ambiguous"]:
                continue
            created.extend(_events_for_record_pair(con, market, from_snapshot_id, to_snapshot_id, entity_id, before, after))

        return _summarize_events(created, from_snapshot_id, to_snapshot_id)


def get_diff_result(
    from_snapshot_id: str,
    to_snapshot_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT event_id, market, from_snapshot_id, to_snapshot_id, entity_id, event_type, severity,
                   confidence, before_record_id, after_record_id, changed_fields_json, explanation, created_at
            FROM diff_events
            WHERE from_snapshot_id = ? AND to_snapshot_id = ?
            ORDER BY event_type, entity_id
            """,
            [from_snapshot_id, to_snapshot_id],
        ).fetchall()
    events = [_event_row(row) for row in rows]
    return _summarize_events(events, from_snapshot_id, to_snapshot_id)


def _events_for_record_pair(
    con: Any,
    market: str,
    from_snapshot_id: str,
    to_snapshot_id: str,
    entity_id: str,
    before_link: dict[str, Any],
    after_link: dict[str, Any],
) -> list[dict[str, Any]]:
    before = before_link["record"]
    after = after_link["record"]
    confidence = after_link["match_score"]
    events: list[dict[str, Any]] = []

    if before["normalized_status"] != after["normalized_status"]:
        if after["normalized_status"] == "Withdrawn":
            event_type = "withdrawn_project"
            severity = "high"
            explanation = "Latest snapshot reports the project status as Withdrawn."
        elif after["normalized_status"] == "Completed":
            event_type = "completed_project"
            severity = "medium"
            explanation = "Latest snapshot reports the project status as Completed."
        else:
            event_type = "status_changed"
            severity = "medium"
            explanation = f"Status changed from {before['normalized_status']} to {after['normalized_status']}."
        events.append(
            _insert_event(
                con,
                market=market,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                event_type=event_type,
                severity=severity,
                confidence=confidence,
                before_record_id=before["record_id"],
                after_record_id=after["record_id"],
                changed_fields={"status": {"before": before["normalized_status"], "after": after["normalized_status"]}},
                explanation=explanation,
            )
        )

    if not capacity_within_tolerance(before.get("capacity_mw"), after.get("capacity_mw")) and before.get("capacity_mw") is not None and after.get("capacity_mw") is not None:
        events.append(
            _insert_event(
                con,
                market=market,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                event_type="capacity_changed",
                severity="medium",
                confidence=confidence,
                before_record_id=before["record_id"],
                after_record_id=after["record_id"],
                changed_fields={"capacity_mw": {"before": before["capacity_mw"], "after": after["capacity_mw"]}},
                explanation="Capacity changed by more than the configured tolerance of the greater of 5 MW or 2%.",
            )
        )

    if before.get("target_cod") and after.get("target_cod"):
        delta_days = (after["target_cod"] - before["target_cod"]).days
        if delta_days > TARGET_COD_MOVE_DAYS:
            events.append(
                _insert_event(
                    con,
                    market=market,
                    from_snapshot_id=from_snapshot_id,
                    to_snapshot_id=to_snapshot_id,
                    entity_id=entity_id,
                    event_type="target_cod_delayed",
                    severity="medium",
                    confidence=confidence,
                    before_record_id=before["record_id"],
                    after_record_id=after["record_id"],
                    changed_fields={"target_cod": {"before": before["target_cod"], "after": after["target_cod"], "delta_days": delta_days}},
                    explanation=f"Target COD moved later by {delta_days} days, above the {TARGET_COD_MOVE_DAYS}-day threshold.",
                )
            )
        elif delta_days < -TARGET_COD_MOVE_DAYS:
            events.append(
                _insert_event(
                    con,
                    market=market,
                    from_snapshot_id=from_snapshot_id,
                    to_snapshot_id=to_snapshot_id,
                    entity_id=entity_id,
                    event_type="target_cod_accelerated",
                    severity="info",
                    confidence=confidence,
                    before_record_id=before["record_id"],
                    after_record_id=after["record_id"],
                    changed_fields={"target_cod": {"before": before["target_cod"], "after": after["target_cod"], "delta_days": delta_days}},
                    explanation=f"Target COD moved earlier by {abs(delta_days)} days, above the {TARGET_COD_MOVE_DAYS}-day threshold.",
                )
            )

    if before["normalized_fuel_type"] != after["normalized_fuel_type"]:
        events.append(
            _insert_event(
                con,
                market=market,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                event_type="fuel_type_changed",
                severity="medium",
                confidence=confidence,
                before_record_id=before["record_id"],
                after_record_id=after["record_id"],
                changed_fields={"fuel_type": {"before": before["normalized_fuel_type"], "after": after["normalized_fuel_type"]}},
                explanation="Normalized fuel type changed for the same resolved project entity.",
            )
        )

    if before.get("normalized_project_name") != after.get("normalized_project_name"):
        events.append(
            _insert_event(
                con,
                market=market,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                event_type="name_changed",
                severity="info",
                confidence=confidence,
                before_record_id=before["record_id"],
                after_record_id=after["record_id"],
                changed_fields={"project_name": {"before": before["project_name"], "after": after["project_name"]}},
                explanation="Project name changed, but entity-resolution evidence linked the records.",
            )
        )

    if before.get("point_of_interconnection") != after.get("point_of_interconnection"):
        events.append(
            _insert_event(
                con,
                market=market,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                event_type="poi_changed",
                severity="medium",
                confidence=confidence,
                before_record_id=before["record_id"],
                after_record_id=after["record_id"],
                changed_fields={
                    "point_of_interconnection": {
                        "before": before.get("point_of_interconnection"),
                        "after": after.get("point_of_interconnection"),
                    }
                },
                explanation="Point of interconnection changed for the same resolved project entity.",
            )
        )

    if not events:
        events.append(
            _insert_event(
                con,
                market=market,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                event_type="unchanged",
                severity="info",
                confidence=confidence,
                before_record_id=before["record_id"],
                after_record_id=after["record_id"],
                changed_fields={},
                explanation="No configured material field changed between these snapshots.",
            )
        )
    return events


def _links_for_snapshot(con: Any, snapshot_id: str) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT l.entity_id, l.match_score, l.match_method, l.match_features_json, l.is_ambiguous,
               r.record_id, r.snapshot_id, r.market, r.queue_id, r.project_name, r.normalized_project_name,
               r.interconnecting_entity, r.county, r.state, r.point_of_interconnection, r.transmission_owner,
               r.fuel_type, r.normalized_fuel_type, r.capacity_mw, r.status, r.normalized_status,
               r.request_date, r.target_cod, r.actual_cod, r.withdrawn_date,
               r.interconnection_agreement_date, r.last_updated_date, r.raw_record_id
        FROM project_entity_links l
        JOIN normalized_project_records r ON r.record_id = l.record_id
        WHERE l.snapshot_id = ?
        ORDER BY r.queue_id NULLS LAST, r.project_name
        """,
        [snapshot_id],
    ).fetchall()
    columns = [
        "record_id",
        "snapshot_id",
        "market",
        "queue_id",
        "project_name",
        "normalized_project_name",
        "interconnecting_entity",
        "county",
        "state",
        "point_of_interconnection",
        "transmission_owner",
        "fuel_type",
        "normalized_fuel_type",
        "capacity_mw",
        "status",
        "normalized_status",
        "request_date",
        "target_cod",
        "actual_cod",
        "withdrawn_date",
        "interconnection_agreement_date",
        "last_updated_date",
        "raw_record_id",
    ]
    links = []
    for row in rows:
        links.append(
            {
                "entity_id": row[0],
                "match_score": float(row[1]),
                "match_method": row[2],
                "match_features": _parse_json(row[3]),
                "is_ambiguous": bool(row[4]),
                "record": dict(zip(columns, row[5:], strict=True)),
            }
        )
    return links


def _insert_event(
    con: Any,
    *,
    market: str,
    from_snapshot_id: str,
    to_snapshot_id: str,
    entity_id: str,
    event_type: str,
    severity: str,
    confidence: float,
    before_record_id: str | None,
    after_record_id: str | None,
    changed_fields: dict[str, Any],
    explanation: str,
) -> dict[str, Any]:
    event_id = new_id("evt")
    created_at = utcnow()
    con.execute(
        """
        INSERT INTO diff_events
        (event_id, market, from_snapshot_id, to_snapshot_id, entity_id, event_type, severity,
         confidence, before_record_id, after_record_id, changed_fields_json, explanation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            event_id,
            market,
            from_snapshot_id,
            to_snapshot_id,
            entity_id,
            event_type,
            severity,
            confidence,
            before_record_id,
            after_record_id,
            stable_json(changed_fields),
            explanation,
            created_at,
        ],
    )
    return {
        "event_id": event_id,
        "market": market,
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "entity_id": entity_id,
        "event_type": event_type,
        "severity": severity,
        "confidence": confidence,
        "before_record_id": before_record_id,
        "after_record_id": after_record_id,
        "changed_fields_json": _json_safe(changed_fields),
        "explanation": explanation,
        "created_at": created_at.isoformat(),
    }


def _event_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "event_id": row[0],
        "market": row[1],
        "from_snapshot_id": row[2],
        "to_snapshot_id": row[3],
        "entity_id": row[4],
        "event_type": row[5],
        "severity": row[6],
        "confidence": float(row[7]),
        "before_record_id": row[8],
        "after_record_id": row[9],
        "changed_fields_json": _parse_json(row[10]),
        "explanation": row[11],
        "created_at": row[12].isoformat() if hasattr(row[12], "isoformat") else row[12],
    }


def _summarize_events(events: list[dict[str, Any]], from_snapshot_id: str, to_snapshot_id: str) -> dict[str, Any]:
    counts = dict(Counter(event["event_type"] for event in events))
    return {
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "counts_by_event_type": counts,
        "event_count": len(events),
        "events": events,
    }


def _json_safe(value: Any) -> Any:
    return json.loads(stable_json(value))


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value
