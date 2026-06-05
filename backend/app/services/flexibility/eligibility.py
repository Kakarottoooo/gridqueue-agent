from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.flexibility.seed import list_flexibility_rules, seed_flexibility_rules
from app.services.utils import new_id, stable_json, utcnow


CONTINGENT_STATUSES = {"proposed", "pending", "directed", "needs_review"}
UNSUPPORTED_STATUSES = {"context_only", "technical_evidence", "superseded"}
FINAL_STATUSES = {"approved", "final"}


def evaluate_eligibility(
    scenario: dict[str, Any],
    *,
    db_path: str | Path | None = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    init_database(db_path)
    seed_flexibility_rules(db_path)
    rules = list_flexibility_rules(jurisdiction=scenario.get("jurisdiction"), include_evidence=True, db_path=db_path)
    if not rules and scenario.get("jurisdiction") != "EVIDENCE":
        rules = list_flexibility_rules(jurisdiction="FERC", include_evidence=False, db_path=db_path)
    results = [_evaluate_rule(rule, scenario) for rule in rules]
    if persist and scenario.get("scenario_id"):
        with connect(db_path) as con:
            for result in results:
                con.execute(
                    """
                    INSERT INTO flexibility_eligibility_results
                    (eligibility_id, scenario_id, rule_id, eligibility_status, confidence,
                     matched_criteria_json, missing_criteria_json, explanation, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        new_id("elig"),
                        scenario["scenario_id"],
                        result["rule_id"],
                        result["eligibility_status"],
                        result["confidence"],
                        stable_json(result["matched_criteria_json"]),
                        stable_json(result["missing_criteria_json"]),
                        result["explanation"],
                        utcnow(),
                    ],
                )
    return results


def _evaluate_rule(rule: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    criteria = rule["eligibility_criteria_json"] or {}
    matched: dict[str, Any] = {}
    missing: dict[str, str] = {}
    mismatched: dict[str, Any] = {}

    expected_jurisdiction = criteria.get("market_or_jurisdiction")
    if expected_jurisdiction and expected_jurisdiction not in {scenario.get("jurisdiction"), scenario.get("market")}:
        mismatched["market_or_jurisdiction"] = {
            "expected": expected_jurisdiction,
            "actual": scenario.get("jurisdiction") or scenario.get("market"),
        }
    elif expected_jurisdiction:
        matched["market_or_jurisdiction"] = expected_jurisdiction

    if "peak_mw_threshold" in criteria:
        threshold = float(criteria["peak_mw_threshold"])
        if float(scenario["peak_mw"]) >= threshold:
            matched["peak_mw_threshold"] = threshold
        else:
            mismatched["peak_mw_threshold"] = {"minimum": threshold, "actual": scenario["peak_mw"]}

    if "commitment_depth_pct_min" in criteria:
        minimum = float(criteria["commitment_depth_pct_min"])
        if float(scenario["commitment_depth_pct"]) >= minimum:
            matched["commitment_depth_pct_min"] = minimum
        else:
            mismatched["commitment_depth_pct_min"] = {"minimum": minimum, "actual": scenario["commitment_depth_pct"]}

    _check_boolean(
        criteria,
        scenario,
        key="curtailability_required",
        scenario_key="dispatchable_or_curtailable",
        matched=matched,
        missing=missing,
        mismatched=mismatched,
    )
    _check_boolean(
        criteria,
        scenario,
        key="dispatchability_required",
        scenario_key="dispatchable_or_curtailable",
        matched=matched,
        missing=missing,
        mismatched=mismatched,
    )
    _check_boolean(
        criteria,
        scenario,
        key="metering_or_control_required",
        scenario_key="metering_or_control_capability",
        matched=matched,
        missing=missing,
        mismatched=mismatched,
    )
    _check_boolean(
        criteria,
        scenario,
        key="colocation_required",
        scenario_key="colocated_generation",
        matched=matched,
        missing=missing,
        mismatched=mismatched,
    )
    _check_boolean(
        criteria,
        scenario,
        key="onsite_generation_required",
        scenario_key="colocated_generation",
        matched=matched,
        missing=missing,
        mismatched=mismatched,
    )

    status = rule["status"]
    if missing:
        eligibility_status = "ambiguous"
        confidence = "Low"
        explanation = "Eligibility is ambiguous because required scenario criteria are missing."
    elif mismatched:
        eligibility_status = "not_eligible"
        confidence = "Medium"
        explanation = "Scenario does not satisfy one or more seeded eligibility criteria."
    elif status in CONTINGENT_STATUSES:
        eligibility_status = "contingent"
        confidence = "Low"
        explanation = f"Rule status is {status}; GridQueue does not treat it as final eligibility."
    elif status in UNSUPPORTED_STATUSES:
        eligibility_status = "unsupported"
        confidence = "Low"
        explanation = f"Record status is {status}; it is context/evidence only and not actionable eligibility."
    elif status in FINAL_STATUSES:
        eligibility_status = "eligible"
        confidence = "Medium"
        explanation = "Scenario satisfies the seeded deterministic criteria for an approved/final rule record."
    else:
        eligibility_status = "unsupported"
        confidence = "Low"
        explanation = f"Unrecognized rule status {status}; manual review required."

    return {
        "rule_id": rule["rule_id"],
        "jurisdiction": rule["jurisdiction"],
        "provision_name": rule["provision_name"],
        "provision_type": rule["provision_type"],
        "rule_status": status,
        "eligibility_status": eligibility_status,
        "confidence": confidence,
        "matched_criteria_json": matched,
        "missing_criteria_json": missing,
        "mismatched_criteria_json": mismatched,
        "explanation": explanation,
        "citations": rule["citations"],
        "source_url": rule["source_url"],
        "granted_benefit_text": rule["granted_benefit_text"],
        "quantified_benefit_json": rule["quantified_benefit_json"],
    }


def _check_boolean(
    criteria: dict[str, Any],
    scenario: dict[str, Any],
    *,
    key: str,
    scenario_key: str,
    matched: dict[str, Any],
    missing: dict[str, str],
    mismatched: dict[str, Any],
) -> None:
    if not criteria.get(key):
        return
    value = scenario.get(scenario_key)
    if value is None:
        missing[key] = f"Scenario must specify {scenario_key}."
    elif bool(value):
        matched[key] = True
    else:
        mismatched[key] = {"required": True, "actual": False}
