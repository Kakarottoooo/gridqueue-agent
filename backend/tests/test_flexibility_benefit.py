from __future__ import annotations

from app.services.flexibility import evaluate_eligibility, estimate_interconnection_benefit, seed_flexibility_rules
from app.services.ingestion import run_fixture_pipeline


def _scenario(**overrides):
    base = {
        "scenario_id": "scenario_benefit",
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


def test_benefit_is_contingent_for_pending_ferc_rule(tmp_path) -> None:
    db_path = tmp_path / "benefit_contingent.duckdb"
    run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    scenario = _scenario()
    eligibility = evaluate_eligibility(scenario, db_path=db_path, persist=False)

    benefit = estimate_interconnection_benefit(scenario, eligibility, min_sample_n=2, db_path=db_path)

    assert benefit["benefit_status"] == "contingent"
    assert benefit["sample_n"] >= 2
    assert benefit["fallback_level"]


def test_benefit_abstains_when_baseline_sample_is_insufficient(tmp_path) -> None:
    db_path = tmp_path / "benefit_insufficient.duckdb"
    run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    scenario = _scenario()
    eligibility = evaluate_eligibility(scenario, db_path=db_path, persist=False)

    benefit = estimate_interconnection_benefit(scenario, eligibility, min_sample_n=100, db_path=db_path)

    assert benefit["benefit_status"] == "insufficient_baseline"
    assert benefit["confidence"] == "Insufficient"


def test_approved_rule_without_quantified_benefit_is_qualitative_only(tmp_path) -> None:
    db_path = tmp_path / "benefit_qualitative.duckdb"
    run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    scenario = _scenario(jurisdiction="SPP")
    eligibility = evaluate_eligibility(scenario, db_path=db_path, persist=False)

    benefit = estimate_interconnection_benefit(scenario, eligibility, min_sample_n=2, db_path=db_path)

    assert benefit["benefit_status"] == "qualitative_only"
    assert benefit["rule_status"] == "approved"
    assert benefit["baseline_metric_id"]
