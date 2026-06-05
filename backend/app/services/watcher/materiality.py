from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.config import project_root


BASE_WEIGHTS: dict[str, float] = {
    "withdrawn_project": 40,
    "completed_project": 35,
    "new_project": 30,
    "status_changed": 25,
    "target_cod_delayed": 25,
    "target_cod_accelerated": 20,
    "capacity_changed": 20,
    "fuel_type_changed": 15,
    "poi_changed": 15,
    "name_changed": 5,
    "ambiguous_match": 0,
    "rule_status_changed": 45,
    "rule_source_changed": 35,
    "rule_needs_review": 30,
    "source_parse_failed": 25,
    "source_unchanged": 0,
    "lead_time_conflict": 30,
    "lead_time_stale": 20,
    "lead_time_source_changed": 25,
    "digest_generated": 0,
}


SUPPRESSED_HARD_ALERT_TYPES = {"ambiguous_match", "name_changed", "source_unchanged"}


def score_change_event(event: dict[str, Any], watchlist: dict[str, Any] | None = None) -> float:
    event_type = str(event.get("event_type") or "")
    score = BASE_WEIGHTS.get(event_type, 10.0)
    before_json = _json(event.get("before_json") or {})
    after_json = _json(event.get("after_json") or {})

    capacity = _capacity_value(after_json) or _capacity_value(before_json)
    if capacity is not None:
        score += min(30.0, math.log10(max(float(capacity), 1.0)) * 10.0)

    if event_type == "capacity_changed":
        delta = _capacity_delta(before_json, after_json)
        if delta is not None:
            score += min(30.0, math.log10(max(abs(delta), 1.0)) * 10.0)

    if event_type == "target_cod_delayed":
        delta_days = _target_cod_delta_days(before_json, after_json)
        if delta_days and delta_days > 365:
            score += 15
        elif delta_days and delta_days > 180:
            score += 10
        elif delta_days and delta_days > 90:
            score += 5

    active_watchlist = watchlist if watchlist is not None else load_watchlist()
    if _matches_watchlist(event, before_json, after_json, active_watchlist):
        score += 10
    return round(score, 4)


def is_hard_alert(event: dict[str, Any]) -> bool:
    if bool(event.get("is_ambiguous")):
        return False
    event_type = str(event.get("event_type") or "")
    if event_type in SUPPRESSED_HARD_ALERT_TYPES:
        return False
    return float(event.get("materiality_score") or score_change_event(event)) >= 20


def rank_change_events(events: list[dict[str, Any]], *, top_n: int = 10) -> dict[str, Any]:
    scored = []
    for event in events:
        materiality_score = float(event.get("materiality_score") or score_change_event(event))
        enriched = {**event, "materiality_score": materiality_score}
        enriched["is_hard_alert"] = bool(event.get("is_hard_alert", is_hard_alert(enriched)))
        scored.append(enriched)

    hard_candidates = [event for event in scored if event["is_hard_alert"]]
    suppressed = [event for event in scored if not event["is_hard_alert"]]
    deduped = _dedup_hard_events(hard_candidates)
    deduped.sort(
        key=lambda item: (
            -float(item["materiality_score"]),
            str(item.get("event_type") or ""),
            str(item.get("entity_or_provision") or ""),
            str(item.get("change_event_id") or ""),
        )
    )
    suppressed.sort(
        key=lambda item: (
            -float(item["materiality_score"]),
            str(item.get("event_type") or ""),
            str(item.get("change_event_id") or ""),
        )
    )
    return {
        "top_events": deduped[:top_n],
        "suppressed_events": suppressed,
        "raw_event_count": len(events),
        "hard_alert_count": len(deduped),
    }


def load_watchlist(path: Path | None = None) -> dict[str, Any]:
    watchlist_path = path or project_root() / "config" / "watchlist.json"
    if not watchlist_path.exists():
        return {"counties": [], "markets": [], "jurisdictions": []}
    return json.loads(watchlist_path.read_text(encoding="utf-8"))


def _dedup_hard_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep_types = {"source_parse_failed", "rule_needs_review", "lead_time_conflict", "lead_time_stale"}
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") in keep_types:
            passthrough.append(event)
            continue
        key = (
            event.get("event_domain"),
            event.get("event_type"),
            event.get("entity_id") or event.get("entity_or_provision"),
            event.get("rule_id"),
            json.dumps(_json(event.get("after_json") or {}), sort_keys=True, default=str),
        )
        existing = deduped.get(key)
        if existing is None or float(event["materiality_score"]) > float(existing["materiality_score"]):
            deduped[key] = event
    return [*deduped.values(), *passthrough]


def _matches_watchlist(
    event: dict[str, Any],
    before_json: dict[str, Any],
    after_json: dict[str, Any],
    watchlist: dict[str, Any],
) -> bool:
    counties = {str(item).lower() for item in watchlist.get("counties", [])}
    markets = {str(item).lower() for item in watchlist.get("markets", [])}
    jurisdictions = {str(item).lower() for item in watchlist.get("jurisdictions", [])}
    county = str(after_json.get("county") or before_json.get("county") or "").lower()
    market = str(event.get("market") or after_json.get("market") or before_json.get("market") or "").lower()
    jurisdiction = str(event.get("jurisdiction") or after_json.get("jurisdiction") or before_json.get("jurisdiction") or "").lower()
    return bool((county and county in counties) or (market and market in markets) or (jurisdiction and jurisdiction in jurisdictions))


def _capacity_value(payload: dict[str, Any]) -> float | None:
    value = payload.get("capacity_mw")
    if value is None and isinstance(payload.get("capacity_mw_change"), dict):
        value = payload["capacity_mw_change"].get("after")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _capacity_delta(before_json: dict[str, Any], after_json: dict[str, Any]) -> float | None:
    if isinstance(after_json.get("changed_fields_json"), dict):
        field = after_json["changed_fields_json"].get("capacity_mw")
        if isinstance(field, dict) and field.get("before") is not None and field.get("after") is not None:
            return float(field["after"]) - float(field["before"])
    before = _capacity_value(before_json)
    after = _capacity_value(after_json)
    if before is None or after is None:
        return None
    return after - before


def _target_cod_delta_days(before_json: dict[str, Any], after_json: dict[str, Any]) -> int | None:
    if isinstance(after_json.get("changed_fields_json"), dict):
        field = after_json["changed_fields_json"].get("target_cod")
        if isinstance(field, dict) and field.get("delta_days") is not None:
            return int(field["delta_days"])
    return None


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return value if isinstance(value, dict) else {}
