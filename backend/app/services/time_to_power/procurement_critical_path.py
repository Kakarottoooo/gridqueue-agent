from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.procurement.lead_time_kb import list_lead_times
from app.services.utils import new_id, stable_json, utcnow


DAYS_PER_MONTH = 30.4375
PROCUREMENT_CAVEAT = (
    "Procurement critical path is a public-data planning proxy only. It is not a procurement quote, OEM RFQ, "
    "supplier commitment, price, engineering design, or delivery guarantee."
)


def compute_procurement_critical_path(
    *,
    scenario_id: str,
    equipment_scope: dict[str, Any],
    stale_threshold_months: int = 18,
    current_date: date | None = None,
    conflict_policy: str = "preserve_all_flag_conflict",
    db_path: str | Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    init_database(db_path)
    today = current_date or date.today()
    items = equipment_scope.get("equipment_scope", [])
    matched_rows: list[dict[str, Any]] = []
    missing_equipment: list[str] = []
    invalid_rows: list[dict[str, Any]] = []

    for item in items:
        equipment_class = item.get("equipment_class")
        if not equipment_class:
            continue
        rows = list_lead_times(equipment_class=equipment_class, db_path=db_path, today=today)
        valid_rows = []
        for row in rows:
            if not row.get("source_url") or not row.get("as_of_date"):
                invalid_rows.append(row)
                continue
            refreshed = {
                **row,
                "is_stale": _is_stale(date.fromisoformat(str(row["as_of_date"])), stale_threshold_months, today),
                "scope_item_id": item.get("scope_item_id"),
                "scope_explanation": item.get("explanation"),
            }
            valid_rows.append(refreshed)
        if not valid_rows:
            missing_equipment.append(equipment_class)
        matched_rows.extend(valid_rows)

    if not matched_rows:
        result = {
            "critical_path_id": new_id("crit"),
            "scenario_id": scenario_id,
            "equipment_scope": equipment_scope,
            "lead_time_rows": [],
            "binding_equipment_class": None,
            "binding_lead_time_low_months": None,
            "binding_lead_time_high_months": None,
            "procurement_low_days": None,
            "procurement_high_days": None,
            "confidence": "insufficient",
            "stale_flag": False,
            "conflict_flag": False,
            "unsupported_flag": True,
            "citations": [],
            "assumptions": {"days_per_month": DAYS_PER_MONTH, "conflict_policy": conflict_policy, "stale_threshold_months": stale_threshold_months},
            "caveats": [PROCUREMENT_CAVEAT, "No supported lead-time rows matched the equipment scope."],
        }
        if persist:
            _store_result(result, db_path)
        return result

    class_ranges = _class_ranges(matched_rows)
    binding = max(class_ranges.values(), key=lambda row: (row["lead_time_high_months"], _risk_rank(row["confidence"])))
    stale_flag = any(row["is_stale"] for row in matched_rows)
    conflict_flag = _has_conflict(matched_rows)
    citations = [
        {
            "citation_label": f"{row['equipment_class']} lead-time source",
            "citation_text": f"{row['lead_time_low_months']}-{row['lead_time_high_months']} months as of {row['as_of_date']}; confidence={row['confidence']}.",
            "source_id": row.get("source_id"),
            "source_url": row["source_url"],
            "source_type": row.get("source_type"),
            "lead_time_id": row["lead_time_id"],
            "as_of_date": row["as_of_date"],
        }
        for row in matched_rows
    ]
    caveats = [PROCUREMENT_CAVEAT]
    if stale_flag:
        caveats.append("One or more lead-time sources are stale under the configured threshold and require manual review.")
    if conflict_flag:
        caveats.append("Multiple sourced lead-time ranges conflict; GridQueue preserves all rows and flags the conflict instead of collapsing precision.")
    if missing_equipment:
        caveats.append(f"No lead-time KB row exists for: {', '.join(sorted(set(missing_equipment)))}.")
    if invalid_rows:
        caveats.append("One or more lead-time rows were ignored because required source_url or as_of_date metadata was missing.")

    result = {
        "critical_path_id": new_id("crit"),
        "scenario_id": scenario_id,
        "equipment_scope": equipment_scope,
        "lead_time_rows": matched_rows,
        "binding_equipment_class": binding["equipment_class"],
        "binding_lead_time_low_months": binding["lead_time_low_months"],
        "binding_lead_time_high_months": binding["lead_time_high_months"],
        "procurement_low_days": round(float(binding["lead_time_low_months"]) * DAYS_PER_MONTH, 2),
        "procurement_high_days": round(float(binding["lead_time_high_months"]) * DAYS_PER_MONTH, 2),
        "confidence": _overall_confidence(matched_rows),
        "stale_flag": stale_flag,
        "conflict_flag": conflict_flag,
        "unsupported_flag": False,
        "citations": citations,
        "assumptions": {"days_per_month": DAYS_PER_MONTH, "conflict_policy": conflict_policy, "stale_threshold_months": stale_threshold_months},
        "caveats": caveats,
    }
    if persist:
        _store_result(result, db_path)
    return result


def _class_ranges(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["equipment_class"], []).append(row)
    result = {}
    for equipment_class, class_rows in grouped.items():
        result[equipment_class] = {
            "equipment_class": equipment_class,
            "lead_time_low_months": min(float(row["lead_time_low_months"]) for row in class_rows),
            "lead_time_high_months": max(float(row["lead_time_high_months"]) for row in class_rows),
            "confidence": _overall_confidence(class_rows),
        }
    return result


def _has_conflict(rows: list[dict[str, Any]]) -> bool:
    grouped: dict[str, set[tuple[float, float]]] = {}
    for row in rows:
        grouped.setdefault(row["equipment_class"], set()).add((float(row["lead_time_low_months"]), float(row["lead_time_high_months"])))
    return any(len(ranges) > 1 for ranges in grouped.values())


def _overall_confidence(rows: list[dict[str, Any]]) -> str:
    ranks = {"high": 3, "medium": 2, "low": 1, "insufficient": 0}
    lowest = min((ranks.get(str(row.get("confidence", "low")).lower(), 1) for row in rows), default=0)
    return {3: "high", 2: "medium", 1: "low", 0: "insufficient"}[lowest]


def _risk_rank(confidence: str) -> int:
    return {"insufficient": 3, "low": 2, "medium": 1, "high": 0}.get(str(confidence).lower(), 2)


def _is_stale(as_of: date, threshold_months: int, today: date) -> bool:
    return (today.year - as_of.year) * 12 + (today.month - as_of.month) >= threshold_months


def _store_result(result: dict[str, Any], db_path: str | Path | None) -> None:
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO procurement_critical_path_results
            (critical_path_id, scenario_id, equipment_scope_json, lead_time_rows_json,
             binding_equipment_class, binding_lead_time_low_months, binding_lead_time_high_months,
             procurement_low_days, procurement_high_days, confidence, stale_flag, conflict_flag,
             unsupported_flag, citations_json, assumptions_json, caveats_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                result["critical_path_id"],
                result["scenario_id"],
                stable_json(result["equipment_scope"]),
                stable_json(result["lead_time_rows"]),
                result["binding_equipment_class"],
                result["binding_lead_time_low_months"],
                result["binding_lead_time_high_months"],
                result["procurement_low_days"],
                result["procurement_high_days"],
                result["confidence"],
                result["stale_flag"],
                result["conflict_flag"],
                result["unsupported_flag"],
                stable_json(result["citations"]),
                stable_json(result["assumptions"]),
                stable_json(result["caveats"]),
                utcnow(),
            ],
        )


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
