from __future__ import annotations

from app.db import reset_database
from app.services.flexibility import evaluate_eligibility, seed_flexibility_rules


def _scenario(**overrides):
    base = {
        "scenario_id": "scenario_test",
        "market": "ERCOT",
        "jurisdiction": "FERC",
        "county": "Reeves",
        "peak_mw": 100,
        "average_load_factor": 0.85,
        "commitment_depth_pct": 25,
        "event_duration_hours": 3,
        "events_per_year": 20,
        "job_mix_json": {},
        "colocated_generation": False,
        "dispatchable_or_curtailable": True,
        "metering_or_control_capability": True,
        "assumption_id": "assumption_test",
    }
    return {**base, **overrides}


def test_proposed_or_pending_ferc_rule_is_contingent_not_eligible(tmp_path) -> None:
    db_path = tmp_path / "eligibility.duckdb"
    reset_database(db_path)
    seed_flexibility_rules(db_path)

    result = evaluate_eligibility(_scenario(), db_path=db_path, persist=False)[0]

    assert result["rule_status"] in {"pending", "proposed"}
    assert result["eligibility_status"] == "contingent"
    assert result["source_url"]


def test_context_and_technical_evidence_are_not_regulatory_eligible(tmp_path) -> None:
    db_path = tmp_path / "evidence.duckdb"
    reset_database(db_path)
    seed_flexibility_rules(db_path)

    ercot = evaluate_eligibility(_scenario(jurisdiction="ERCOT"), db_path=db_path, persist=False)[0]
    evidence = evaluate_eligibility(_scenario(jurisdiction="EVIDENCE"), db_path=db_path, persist=False)[0]

    assert ercot["eligibility_status"] == "unsupported"
    assert ercot["rule_status"] == "context_only"
    assert evidence["eligibility_status"] == "unsupported"
    assert evidence["rule_status"] == "technical_evidence"


def test_missing_metering_or_control_criteria_are_ambiguous(tmp_path) -> None:
    db_path = tmp_path / "missing.duckdb"
    reset_database(db_path)
    seed_flexibility_rules(db_path)

    result = evaluate_eligibility(
        _scenario(metering_or_control_capability=None),
        db_path=db_path,
        persist=False,
    )[0]

    assert result["eligibility_status"] == "ambiguous"
    assert "metering_or_control_required" in result["missing_criteria_json"]


def test_every_eligibility_result_has_explanation_and_citation(tmp_path) -> None:
    db_path = tmp_path / "citations.duckdb"
    reset_database(db_path)
    seed_flexibility_rules(db_path)

    results = evaluate_eligibility(_scenario(), db_path=db_path, persist=False)

    assert all(result["explanation"] for result in results)
    assert all(result["citations"] and result["citations"][0]["source_url"] for result in results)
