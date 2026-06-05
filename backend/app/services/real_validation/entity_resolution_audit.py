from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.config import project_root
from app.db import connect, init_database
from app.services.utils import stable_json
from app.services.real_validation.common import month_label, real_reports_dir


AUDIT_COLUMNS = [
    "from_snapshot_id",
    "to_snapshot_id",
    "from_record_id",
    "to_record_id",
    "entity_id",
    "project_name_before",
    "project_name_after",
    "queue_id_before",
    "queue_id_after",
    "capacity_before",
    "capacity_after",
    "fuel_type_before",
    "fuel_type_after",
    "county_before",
    "county_after",
    "status_before",
    "status_after",
    "target_cod_before",
    "target_cod_after",
    "match_score",
    "match_features_json",
    "ambiguity_reason",
    "system_label",
    "manual_label",
    "manual_reviewer",
    "manual_review_notes",
    "evidence_summary",
    "source_file_hash_before",
    "source_file_hash_after",
]

MANUAL_LABEL_VALUES = [
    "same_entity",
    "different_entity",
    "true_new",
    "true_removed",
    "true_withdrawn",
    "true_completed",
    "reclassification",
    "ambiguous_needs_review",
    "insufficient_evidence",
]


def build_ercot_entity_resolution_audit(
    *,
    from_snapshot_id: str,
    to_snapshot_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    rows: list[dict[str, Any]] = []
    ambiguous_rows: list[dict[str, Any]] = []
    with connect(db_path) as con:
        hashes = _snapshot_hashes(con, from_snapshot_id, to_snapshot_id)
        pair_links = con.execute(
            """
            SELECT before_l.entity_id,
                   before_l.record_id,
                   after_l.record_id,
                   after_l.match_score,
                   after_l.match_method,
                   after_l.match_features_json,
                   after_l.is_ambiguous
            FROM project_entity_links before_l
            JOIN project_entity_links after_l ON after_l.entity_id = before_l.entity_id
            WHERE before_l.snapshot_id = ? AND after_l.snapshot_id = ?
            ORDER BY after_l.is_ambiguous DESC, after_l.match_score DESC, before_l.entity_id
            """,
            [from_snapshot_id, to_snapshot_id],
        ).fetchall()
        for entity_id, before_record_id, after_record_id, match_score, method, features_json, is_ambiguous in pair_links:
            before = _record(con, before_record_id)
            after = _record(con, after_record_id)
            features = _parse_json(features_json)
            row = _audit_row(
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                before=before,
                after=after,
                match_score=float(match_score),
                match_features=features,
                ambiguity_reason=_ambiguity_reason(features) if is_ambiguous else "",
                system_label=_match_label(before, after, float(match_score), method, bool(is_ambiguous)),
                evidence_summary=_match_evidence_summary(before, after, float(match_score), method, bool(is_ambiguous)),
                source_file_hash_before=hashes["before"],
                source_file_hash_after=hashes["after"],
            )
            rows.append(row)
            if is_ambiguous:
                ambiguous_rows.append(row)

        event_rows = con.execute(
            """
            SELECT event_id, entity_id, event_type, confidence, before_record_id, after_record_id,
                   changed_fields_json, explanation
            FROM diff_events
            WHERE from_snapshot_id = ? AND to_snapshot_id = ?
              AND event_type IN ('new_project', 'removed_project', 'withdrawn_project', 'completed_project',
                                 'fuel_type_changed', 'name_changed', 'capacity_changed',
                                 'target_cod_delayed', 'target_cod_accelerated', 'status_changed',
                                 'ambiguous_match')
            ORDER BY event_type, entity_id
            """,
            [from_snapshot_id, to_snapshot_id],
        ).fetchall()
        existing_keys = {(row["from_record_id"], row["to_record_id"], row["system_label"]) for row in rows}
        for event_id, entity_id, event_type, confidence, before_record_id, after_record_id, changed_fields_json, explanation in event_rows:
            before = _record(con, before_record_id)
            after = _record(con, after_record_id)
            system_label = _event_label(event_type, changed_fields_json)
            key = (before.get("record_id"), after.get("record_id"), system_label)
            if key in existing_keys:
                continue
            row = _audit_row(
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                entity_id=entity_id,
                before=before,
                after=after,
                match_score=float(confidence),
                match_features={"diff_event_id": event_id, "event_type": event_type, "changed_fields": _parse_json(changed_fields_json)},
                ambiguity_reason="",
                system_label=system_label,
                evidence_summary=f"{event_type}: {explanation}",
                source_file_hash_before=hashes["before"],
                source_file_hash_after=hashes["after"],
            )
            rows.append(row)
            if system_label == "ambiguous_needs_review":
                ambiguous_rows.append(row)
            existing_keys.add(key)

    start = month_label(_snapshot_date(from_snapshot_id, db_path))
    end = month_label(_snapshot_date(to_snapshot_id, db_path))
    audit_dir = real_reports_dir() / "entity_resolution_audit"
    manual_dir = real_reports_dir() / "manual_review"
    matches_path = audit_dir / f"ercot_matches_{start}_to_{end}.csv"
    ambiguous_path = audit_dir / f"ercot_ambiguous_{start}_to_{end}.csv"
    manual_path = manual_dir / f"ercot_manual_review_template_{start}_to_{end}.csv"
    _write_csv(matches_path, rows)
    _write_csv(ambiguous_path, ambiguous_rows)
    manual_candidates = _manual_review_candidates(rows)
    _write_csv(manual_path, manual_candidates)

    counts = _counts(rows)
    return {
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "matches_path": str(matches_path.relative_to(project_root())),
        "ambiguous_path": str(ambiguous_path.relative_to(project_root())),
        "manual_review_path": str(manual_path.relative_to(project_root())),
        "manual_label_values": MANUAL_LABEL_VALUES,
        "row_count": len(rows),
        "ambiguous_count": len(ambiguous_rows),
        "manual_review_candidate_count": len(manual_candidates),
        **counts,
    }


def _audit_row(
    *,
    from_snapshot_id: str,
    to_snapshot_id: str,
    entity_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
    match_score: float,
    match_features: dict[str, Any],
    ambiguity_reason: str,
    system_label: str,
    evidence_summary: str,
    source_file_hash_before: str,
    source_file_hash_after: str,
) -> dict[str, Any]:
    return {
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "from_record_id": before.get("record_id") or "",
        "to_record_id": after.get("record_id") or "",
        "entity_id": entity_id,
        "project_name_before": before.get("project_name") or "",
        "project_name_after": after.get("project_name") or "",
        "queue_id_before": before.get("queue_id") or "",
        "queue_id_after": after.get("queue_id") or "",
        "capacity_before": before.get("capacity_mw") if before.get("capacity_mw") is not None else "",
        "capacity_after": after.get("capacity_mw") if after.get("capacity_mw") is not None else "",
        "fuel_type_before": before.get("normalized_fuel_type") or "",
        "fuel_type_after": after.get("normalized_fuel_type") or "",
        "county_before": before.get("county") or "",
        "county_after": after.get("county") or "",
        "status_before": before.get("normalized_status") or "",
        "status_after": after.get("normalized_status") or "",
        "target_cod_before": _date_text(before.get("target_cod")),
        "target_cod_after": _date_text(after.get("target_cod")),
        "match_score": round(match_score, 4),
        "match_features_json": stable_json(match_features),
        "ambiguity_reason": ambiguity_reason,
        "system_label": system_label,
        "manual_label": "",
        "manual_reviewer": "",
        "manual_review_notes": "",
        "evidence_summary": evidence_summary,
        "source_file_hash_before": source_file_hash_before,
        "source_file_hash_after": source_file_hash_after,
    }


def _match_label(before: dict[str, Any], after: dict[str, Any], score: float, method: str, is_ambiguous: bool) -> str:
    if is_ambiguous:
        return "ambiguous_needs_review"
    if before.get("queue_id") and before.get("queue_id") == after.get("queue_id"):
        return "auto_verified_exact_id"
    if score >= 0.76:
        return "system_suggested_same_entity_fuzzy"
    if method == "new_entity":
        return "system_suggested_new_entity"
    return "system_suggested_possible_match"


def _event_label(event_type: str, changed_fields_json: Any) -> str:
    if event_type == "new_project":
        return "system_suggested_true_new"
    if event_type == "ambiguous_match":
        return "ambiguous_needs_review"
    if event_type == "removed_project":
        return "system_suggested_true_removed_not_withdrawn"
    if event_type == "withdrawn_project":
        return "system_suggested_true_withdrawn"
    if event_type == "completed_project":
        return "system_suggested_true_completed"
    if event_type == "fuel_type_changed":
        return "possible_reclassification"
    if event_type == "name_changed":
        return "possible_id_name_drift"
    if event_type in {"capacity_changed", "target_cod_delayed", "target_cod_accelerated", "status_changed"}:
        return f"system_suggested_{event_type}"
    return f"system_suggested_{event_type}"


def _match_evidence_summary(before: dict[str, Any], after: dict[str, Any], score: float, method: str, is_ambiguous: bool) -> str:
    if is_ambiguous:
        return f"Ambiguous candidate set; top score={score}, method={method}; no forced hard alert."
    if before.get("queue_id") and before.get("queue_id") == after.get("queue_id"):
        return f"Exact queue/INR ID match {before.get('queue_id')} across snapshots."
    return f"System match by {method}, score={score}; reviewer should spot-check if material."


def _ambiguity_reason(features: dict[str, Any]) -> str:
    reason = features.get("reason") if isinstance(features, dict) else None
    return str(reason or "Top candidates were too close to force a match.")


def _manual_review_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = [
        row
        for row in rows
        if row["system_label"]
        not in {"auto_verified_exact_id", "system_suggested_true_new", "system_suggested_true_removed_not_withdrawn"}
    ]
    priority.sort(
        key=lambda row: (
            0 if row["system_label"] == "ambiguous_needs_review" else 1,
            -float(row["match_score"] or 0),
            row["project_name_after"] or row["project_name_before"],
        )
    )
    return priority[:50]


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    labels = [row["system_label"] for row in rows]
    return {
        "exact_matches": labels.count("auto_verified_exact_id"),
        "fuzzy_matches": labels.count("system_suggested_same_entity_fuzzy"),
        "ambiguous_matches": labels.count("ambiguous_needs_review"),
        "true_additions": labels.count("system_suggested_true_new"),
        "true_removals_or_missing": labels.count("system_suggested_true_removed_not_withdrawn"),
        "true_withdrawals": labels.count("system_suggested_true_withdrawn"),
        "true_completed": labels.count("system_suggested_true_completed"),
        "reclassifications": labels.count("possible_reclassification"),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in AUDIT_COLUMNS})


def _record(con: Any, record_id: str | None) -> dict[str, Any]:
    if not record_id:
        return {}
    row = con.execute(
        """
        SELECT record_id, snapshot_id, market, queue_id, project_name, county, state,
               point_of_interconnection, normalized_fuel_type, capacity_mw, normalized_status,
               target_cod, raw_record_id
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
        "target_cod": row[11],
        "raw_record_id": row[12],
    }


def _snapshot_hashes(con: Any, from_snapshot_id: str, to_snapshot_id: str) -> dict[str, str]:
    rows = con.execute(
        "SELECT snapshot_id, file_hash FROM snapshots WHERE snapshot_id IN (?, ?)",
        [from_snapshot_id, to_snapshot_id],
    ).fetchall()
    lookup = {row[0]: row[1] for row in rows}
    return {"before": lookup.get(from_snapshot_id, ""), "after": lookup.get(to_snapshot_id, "")}


def _snapshot_date(snapshot_id: str, db_path: str | Path | None) -> str:
    with connect(db_path) as con:
        row = con.execute("SELECT snapshot_date FROM snapshots WHERE snapshot_id = ?", [snapshot_id]).fetchone()
    if not row:
        return snapshot_id
    return row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])


def _date_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value
