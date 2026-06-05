from __future__ import annotations

import json
from typing import Any

from app.services.utils import new_id, stable_json, utcnow
from app.services.watcher.materiality import is_hard_alert, score_change_event


def insert_change_event(
    con: Any,
    *,
    event_domain: str,
    event_type: str,
    jurisdiction: str | None = None,
    market: str | None = None,
    entity_or_provision: str | None = None,
    entity_id: str | None = None,
    rule_id: str | None = None,
    source_snapshot_id: str | None = None,
    from_snapshot_id: str | None = None,
    to_snapshot_id: str | None = None,
    source_url: str | None = None,
    before_json: dict[str, Any] | None = None,
    after_json: dict[str, Any] | None = None,
    confidence: float = 1.0,
    is_ambiguous: bool = False,
    is_hard_alert_value: bool | None = None,
    explanation: str,
    citation_ids: list[str] | None = None,
    materiality_score: float | None = None,
) -> dict[str, Any]:
    before = before_json or {}
    after = after_json or {}
    event = {
        "event_domain": event_domain,
        "event_type": event_type,
        "jurisdiction": jurisdiction,
        "market": market,
        "entity_or_provision": entity_or_provision,
        "entity_id": entity_id,
        "rule_id": rule_id,
        "source_snapshot_id": source_snapshot_id,
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "source_url": source_url,
        "before_json": before,
        "after_json": after,
        "confidence": confidence,
        "is_ambiguous": is_ambiguous,
    }
    score = materiality_score if materiality_score is not None else score_change_event(event)
    event["materiality_score"] = score
    hard_alert = is_hard_alert_value if is_hard_alert_value is not None else is_hard_alert(event)
    change_event_id = new_id("chg")
    now = utcnow()
    con.execute(
        """
        INSERT INTO change_events
        (change_event_id, event_domain, event_type, jurisdiction, market, entity_or_provision,
         entity_id, rule_id, source_snapshot_id, from_snapshot_id, to_snapshot_id, source_url,
         before_json, after_json, materiality_score, confidence, is_ambiguous, is_hard_alert,
         explanation, citation_ids_json, detected_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            change_event_id,
            event_domain,
            event_type,
            jurisdiction,
            market,
            entity_or_provision,
            entity_id,
            rule_id,
            source_snapshot_id,
            from_snapshot_id,
            to_snapshot_id,
            source_url,
            stable_json(before),
            stable_json(after),
            score,
            confidence,
            is_ambiguous,
            hard_alert,
            explanation,
            stable_json(citation_ids or []),
            now,
            now,
        ],
    )
    return {
        "change_event_id": change_event_id,
        **event,
        "before_json": _json(before),
        "after_json": _json(after),
        "is_hard_alert": hard_alert,
        "explanation": explanation,
        "citation_ids_json": citation_ids or [],
        "detected_at": now.isoformat(),
        "created_at": now.isoformat(),
    }


def row_to_change_event(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "change_event_id": row[0],
        "event_domain": row[1],
        "event_type": row[2],
        "jurisdiction": row[3],
        "market": row[4],
        "entity_or_provision": row[5],
        "entity_id": row[6],
        "rule_id": row[7],
        "source_snapshot_id": row[8],
        "from_snapshot_id": row[9],
        "to_snapshot_id": row[10],
        "source_url": row[11],
        "before_json": json.loads(row[12]) if isinstance(row[12], str) else row[12],
        "after_json": json.loads(row[13]) if isinstance(row[13], str) else row[13],
        "materiality_score": row[14],
        "confidence": row[15],
        "is_ambiguous": bool(row[16]),
        "is_hard_alert": bool(row[17]),
        "explanation": row[18],
        "citation_ids_json": json.loads(row[19]) if isinstance(row[19], str) else row[19],
        "detected_at": row[20].isoformat() if hasattr(row[20], "isoformat") else row[20],
        "created_at": row[21].isoformat() if hasattr(row[21], "isoformat") else row[21],
    }


def change_event_select_sql() -> str:
    return """
        SELECT change_event_id, event_domain, event_type, jurisdiction, market, entity_or_provision,
               entity_id, rule_id, source_snapshot_id, from_snapshot_id, to_snapshot_id, source_url,
               before_json, after_json, materiality_score, confidence, is_ambiguous, is_hard_alert,
               explanation, citation_ids_json, detected_at, created_at
        FROM change_events
    """


def _json(value: Any) -> Any:
    return json.loads(stable_json(value))
