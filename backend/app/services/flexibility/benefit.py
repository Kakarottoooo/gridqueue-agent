from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.metrics import compute_metric_rollup


FINAL_BENEFIT_STATUSES = {"approved", "final"}


def estimate_interconnection_benefit(
    scenario: dict[str, Any],
    eligibility_results: list[dict[str, Any]],
    *,
    baseline_project_type: str = "Battery",
    min_sample_n: int = 30,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    metric = compute_metric_rollup(
        market=scenario["market"],
        county=scenario.get("county"),
        fuel_type=baseline_project_type,
        min_sample_n=min_sample_n,
        db_path=db_path,
    )
    baseline_timeline_days = metric.get("p75_duration_days") or metric.get("median_duration_days")
    baseline_trace = {
        "baseline_metric_id": metric.get("metric_id"),
        "baseline_timeline_days": baseline_timeline_days,
        "sample_n": metric.get("sample_n"),
        "fallback_level": metric.get("fallback_level"),
        "confidence": metric.get("confidence"),
        "source_snapshot_id": metric.get("source_snapshot_id"),
        "baseline_project_type": baseline_project_type,
    }
    if metric.get("confidence") == "Insufficient" or not baseline_timeline_days:
        return {
            **baseline_trace,
            "with_flex_timeline_days": None,
            "estimated_timeline_delta_days": None,
            "benefit_status": "insufficient_baseline",
            "rule_id": None,
            "rule_status": None,
            "explanation": "No-flexibility baseline is insufficient or lacks a duration proxy; GridQueue abstains from timeline benefit estimates.",
        }

    relevant = _select_relevant_result(eligibility_results)
    if not relevant:
        return {
            **baseline_trace,
            "with_flex_timeline_days": None,
            "estimated_timeline_delta_days": None,
            "benefit_status": "unsupported",
            "rule_id": None,
            "rule_status": None,
            "explanation": "No relevant flexibility rule was found for this scenario.",
        }

    if relevant["eligibility_status"] in {"not_eligible", "unsupported", "ambiguous"}:
        return {
            **baseline_trace,
            "with_flex_timeline_days": None,
            "estimated_timeline_delta_days": None,
            "benefit_status": "unsupported" if relevant["eligibility_status"] != "ambiguous" else "contingent",
            "rule_id": relevant["rule_id"],
            "rule_status": relevant["rule_status"],
            "explanation": f"Eligibility is {relevant['eligibility_status']}; no timeline benefit is estimated.",
        }

    if relevant["rule_status"] not in FINAL_BENEFIT_STATUSES:
        return {
            **baseline_trace,
            "with_flex_timeline_days": None,
            "estimated_timeline_delta_days": None,
            "benefit_status": "contingent",
            "rule_id": relevant["rule_id"],
            "rule_status": relevant["rule_status"],
            "explanation": f"Rule status is {relevant['rule_status']}; any benefit is contingent and not quantified.",
        }

    quantified = relevant.get("quantified_benefit_json") or {}
    delta = _quantified_delta(quantified, float(scenario["commitment_depth_pct"]))
    if delta is None:
        return {
            **baseline_trace,
            "with_flex_timeline_days": None,
            "estimated_timeline_delta_days": None,
            "benefit_status": "qualitative_only",
            "rule_id": relevant["rule_id"],
            "rule_status": relevant["rule_status"],
            "explanation": "Relevant rule is approved/final, but seeded data has no cited quantified timeline benefit.",
        }

    bounded_delta = min(float(delta), float(baseline_timeline_days))
    return {
        **baseline_trace,
        "with_flex_timeline_days": round(float(baseline_timeline_days) - bounded_delta, 2),
        "estimated_timeline_delta_days": round(bounded_delta, 2),
        "benefit_status": "quantified",
        "rule_id": relevant["rule_id"],
        "rule_status": relevant["rule_status"],
        "explanation": "Quantified benefit is calculated only from seeded quantified_benefit_json and bounded by the baseline timeline.",
    }


def _select_relevant_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    priority = {"eligible": 0, "contingent": 1, "ambiguous": 2, "unsupported": 3, "not_eligible": 4}
    return min(results, key=lambda result: priority.get(result["eligibility_status"], 99), default=None)


def _quantified_delta(quantified: dict[str, Any], commitment_depth_pct: float) -> float | None:
    points = quantified.get("timeline_delta_days_by_commitment_pct") or []
    eligible = [
        float(point["estimated_timeline_delta_days"])
        for point in points
        if float(point["commitment_depth_pct"]) <= commitment_depth_pct
    ]
    return max(eligible) if eligible else None
