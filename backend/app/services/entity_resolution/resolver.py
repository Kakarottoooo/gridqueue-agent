from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.normalization.normalizer import normalize_company, normalize_project_name
from app.services.utils import new_id, stable_json, utcnow


HIGH_CONFIDENCE_MATCH = 0.76
POSSIBLE_MATCH = 0.58
AMBIGUITY_DELTA = 0.05


@dataclass(frozen=True)
class MatchResult:
    score: float
    method: str
    features: dict[str, Any]


def similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def compatible_fuel(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return {left, right} in ({"Solar", "Hybrid"}, {"Battery", "Hybrid"})


def capacity_within_tolerance(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= max(5.0, 0.02 * max(abs(left), abs(right)))


def days_between(left: date | None, right: date | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left - right).days)


def compare_records(before: dict[str, Any], after: dict[str, Any]) -> MatchResult:
    name_score = similarity(before.get("normalized_project_name"), after.get("normalized_project_name"))
    entity_score = similarity(
        normalize_company(before.get("interconnecting_entity")),
        normalize_company(after.get("interconnecting_entity")),
    )
    poi_score = similarity(
        normalize_project_name(before.get("point_of_interconnection")),
        normalize_project_name(after.get("point_of_interconnection")),
    )
    cod_days = days_between(before.get("target_cod"), after.get("target_cod"))
    capacity_match = capacity_within_tolerance(before.get("capacity_mw"), after.get("capacity_mw"))
    capacity_delta = (
        None
        if before.get("capacity_mw") is None or after.get("capacity_mw") is None
        else abs(float(before["capacity_mw"]) - float(after["capacity_mw"]))
    )

    score = 0.0
    features: dict[str, Any] = {
        "exact_queue_id": bool(before.get("queue_id") and before.get("queue_id") == after.get("queue_id")),
        "name_similarity": round(name_score, 4),
        "interconnecting_entity_similarity": round(entity_score, 4),
        "county_match": bool(before.get("county") and before.get("county") == after.get("county")),
        "state_match": bool(before.get("state") and before.get("state") == after.get("state")),
        "fuel_compatible": compatible_fuel(before.get("normalized_fuel_type"), after.get("normalized_fuel_type")),
        "capacity_within_tolerance": capacity_match,
        "capacity_delta_mw": capacity_delta,
        "poi_similarity": round(poi_score, 4),
        "target_cod_days_apart": cod_days,
    }

    if features["exact_queue_id"]:
        score += 0.38
    if name_score >= 0.90:
        score += 0.22
    elif name_score >= 0.75:
        score += 0.14
    if entity_score >= 0.85:
        score += 0.10
    if features["county_match"]:
        score += 0.09
    if features["state_match"]:
        score += 0.04
    if features["fuel_compatible"]:
        score += 0.10
    if capacity_match:
        score += 0.10
    elif capacity_delta is not None and capacity_delta <= max(10.0, 0.10 * max(abs(before["capacity_mw"]), abs(after["capacity_mw"]))):
        score += 0.04
    if poi_score >= 0.80:
        score += 0.07
    if cod_days is not None and cod_days <= 180:
        score += 0.04

    score = min(round(score, 4), 1.0)
    if score >= HIGH_CONFIDENCE_MATCH:
        method = "high_confidence_match"
    elif score >= POSSIBLE_MATCH:
        method = "possible_match"
    else:
        method = "no_match"
    return MatchResult(score=score, method=method, features=features)


def resolve_market(market: str, db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        con.execute("DELETE FROM project_entity_links WHERE snapshot_id IN (SELECT snapshot_id FROM snapshots WHERE market = ?)", [market])
        con.execute("DELETE FROM project_entities WHERE market = ?", [market])

        snapshots = con.execute(
            "SELECT snapshot_id FROM snapshots WHERE market = ? ORDER BY snapshot_date, snapshot_id",
            [market],
        ).fetchall()
        snapshot_ids = [row[0] for row in snapshots]
        linked = 0
        ambiguous = 0
        new_entities = 0

        for index, snapshot_id in enumerate(snapshot_ids):
            records = _records_for_snapshot(con, snapshot_id)
            if index == 0:
                for record in records:
                    entity_id = _create_entity(con, record, snapshot_id)
                    new_entities += 1
                    _create_link(
                        con,
                        entity_id=entity_id,
                        record=record,
                        score=1.0,
                        method="first_snapshot_seed",
                        features={"reason": "First snapshot for market; seeded as project entity."},
                        is_ambiguous=False,
                    )
                    linked += 1
                continue

            prior_snapshot_id = snapshot_ids[index - 1]
            candidates = _latest_records_for_snapshot(con, prior_snapshot_id)
            used_entities: set[str] = set()
            for record in records:
                ranked = _rank_candidates(record, candidates)
                top = ranked[0] if ranked else None
                second = ranked[1] if len(ranked) > 1 else None
                is_ambiguous = bool(
                    top
                    and top["match"].score >= POSSIBLE_MATCH
                    and second
                    and top["match"].score - second["match"].score <= AMBIGUITY_DELTA
                )

                if top and top["match"].score >= POSSIBLE_MATCH and not is_ambiguous and top["entity_id"] not in used_entities:
                    entity_id = top["entity_id"]
                    used_entities.add(entity_id)
                    _update_entity(con, entity_id, record, snapshot_id)
                    _create_link(
                        con,
                        entity_id=entity_id,
                        record=record,
                        score=top["match"].score,
                        method=top["match"].method,
                        features={
                            **top["match"].features,
                            "candidate_record_id": top["record"]["record_id"],
                            "candidate_entity_id": entity_id,
                        },
                        is_ambiguous=False,
                    )
                    linked += 1
                    continue

                entity_id = _create_entity(con, record, snapshot_id)
                new_entities += 1
                if is_ambiguous and top:
                    ambiguous += 1
                    features = {
                        "reason": "Top candidate scores are too close; link not forced.",
                        "candidate_entities": [
                            {
                                "entity_id": item["entity_id"],
                                "record_id": item["record"]["record_id"],
                                "score": item["match"].score,
                                "method": item["match"].method,
                                "features": item["match"].features,
                            }
                            for item in ranked[:3]
                        ],
                    }
                    _create_link(
                        con,
                        entity_id=entity_id,
                        record=record,
                        score=top["match"].score,
                        method="ambiguous_possible_match",
                        features=features,
                        is_ambiguous=True,
                    )
                else:
                    _create_link(
                        con,
                        entity_id=entity_id,
                        record=record,
                        score=top["match"].score if top else 0.0,
                        method="new_entity",
                        features={
                            "reason": "No prior candidate reached the possible-match threshold.",
                            "best_candidate": _candidate_summary(top) if top else None,
                        },
                        is_ambiguous=False,
                    )
                linked += 1
    return {"market": market, "snapshots": snapshot_ids, "linked_records": linked, "ambiguous_links": ambiguous, "entities": new_entities}


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return {
        "entity_id": candidate["entity_id"],
        "record_id": candidate["record"]["record_id"],
        "score": candidate["match"].score,
        "method": candidate["match"].method,
    }


def _rank_candidates(record: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        match = compare_records(candidate["record"], record)
        ranked.append({"entity_id": candidate["entity_id"], "record": candidate["record"], "match": match})
    ranked.sort(key=lambda item: item["match"].score, reverse=True)
    return ranked


def _records_for_snapshot(con: Any, snapshot_id: str) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT record_id, snapshot_id, market, queue_id, project_name, normalized_project_name,
               interconnecting_entity, county, state, point_of_interconnection, transmission_owner,
               fuel_type, normalized_fuel_type, capacity_mw, status, normalized_status,
               request_date, target_cod, actual_cod, withdrawn_date, interconnection_agreement_date,
               last_updated_date, raw_record_id
        FROM normalized_project_records
        WHERE snapshot_id = ?
        ORDER BY queue_id NULLS LAST, project_name
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
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _latest_records_for_snapshot(con: Any, snapshot_id: str) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT l.entity_id, r.record_id, r.snapshot_id, r.market, r.queue_id, r.project_name,
               r.normalized_project_name, r.interconnecting_entity, r.county, r.state,
               r.point_of_interconnection, r.transmission_owner, r.fuel_type,
               r.normalized_fuel_type, r.capacity_mw, r.status, r.normalized_status,
               r.request_date, r.target_cod, r.actual_cod, r.withdrawn_date,
               r.interconnection_agreement_date, r.last_updated_date, r.raw_record_id
        FROM project_entity_links l
        JOIN normalized_project_records r ON r.record_id = l.record_id
        WHERE l.snapshot_id = ?
          AND l.is_ambiguous = FALSE
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
    candidates = []
    for row in rows:
        candidates.append({"entity_id": row[0], "record": dict(zip(columns, row[1:], strict=True))})
    return candidates


def _create_entity(con: Any, record: dict[str, Any], snapshot_id: str) -> str:
    entity_id = new_id("ent")
    now = utcnow()
    con.execute(
        """
        INSERT INTO project_entities
        (entity_id, market, canonical_name, canonical_county, canonical_state, canonical_fuel_type,
         first_seen_snapshot_id, latest_seen_snapshot_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            entity_id,
            record["market"],
            record["project_name"],
            record["county"],
            record["state"],
            record["normalized_fuel_type"],
            snapshot_id,
            snapshot_id,
            now,
            now,
        ],
    )
    return entity_id


def _update_entity(con: Any, entity_id: str, record: dict[str, Any], snapshot_id: str) -> None:
    con.execute(
        """
        UPDATE project_entities
        SET canonical_name = ?, canonical_county = ?, canonical_state = ?, canonical_fuel_type = ?,
            latest_seen_snapshot_id = ?, updated_at = ?
        WHERE entity_id = ?
        """,
        [
            record["project_name"],
            record["county"],
            record["state"],
            record["normalized_fuel_type"],
            snapshot_id,
            utcnow(),
            entity_id,
        ],
    )


def _create_link(
    con: Any,
    *,
    entity_id: str,
    record: dict[str, Any],
    score: float,
    method: str,
    features: dict[str, Any],
    is_ambiguous: bool,
) -> str:
    link_id = new_id("link")
    con.execute(
        """
        INSERT INTO project_entity_links
        (link_id, entity_id, record_id, snapshot_id, match_score, match_method, match_features_json,
         is_ambiguous, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            link_id,
            entity_id,
            record["record_id"],
            record["snapshot_id"],
            score,
            method,
            stable_json(features),
            is_ambiguous,
            utcnow(),
        ],
    )
    return link_id

