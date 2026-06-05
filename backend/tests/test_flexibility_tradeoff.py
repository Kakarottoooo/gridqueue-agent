from __future__ import annotations

from app.services.flexibility import get_compute_assumption, run_tradeoff_sweep, seed_flexibility_rules
from app.services.ingestion import run_fixture_pipeline


def test_tradeoff_has_no_hard_recommendation_for_qualitative_or_contingent_benefits(tmp_path) -> None:
    db_path = tmp_path / "tradeoff_qualitative.duckdb"
    run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    assumption = get_compute_assumption(db_path=db_path)

    result = run_tradeoff_sweep(
        market="ERCOT",
        jurisdiction="FERC",
        county="Reeves",
        peak_mw=100,
        average_load_factor=0.85,
        event_duration_hours=3,
        events_per_year=20,
        job_mix_json={},
        colocated_generation=False,
        dispatchable_or_curtailable=True,
        metering_or_control_capability=True,
        assumption=assumption,
        min_sample_n=2,
        value_per_day_usd=1_000_000,
        db_path=db_path,
    )

    assert result["recommendation"]["mode"] == "scenario_comparison_only"
    assert all(point["net_benefit_score"] is None for point in result["tradeoff_points"])


def test_tradeoff_recommends_max_net_benefit_for_quantified_fixture_rule(tmp_path) -> None:
    db_path = tmp_path / "tradeoff_quantified.duckdb"
    run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    assumption = get_compute_assumption(db_path=db_path)

    result = run_tradeoff_sweep(
        market="ERCOT",
        jurisdiction="DEMO",
        county="Reeves",
        peak_mw=100,
        average_load_factor=0.85,
        event_duration_hours=3,
        events_per_year=20,
        job_mix_json={},
        colocated_generation=False,
        dispatchable_or_curtailable=True,
        metering_or_control_capability=True,
        assumption=assumption,
        min_sample_n=2,
        value_per_day_usd=1_000_000,
        db_path=db_path,
    )

    scored = [point for point in result["tradeoff_points"] if point["net_benefit_score"] is not None]
    selected = max(scored, key=lambda point: point["net_benefit_score"])

    assert result["recommendation"]["mode"] == "max_net_benefit_under_assumptions"
    assert result["recommendation"]["selected_tradeoff_id"] == selected["tradeoff_id"]
    assert selected["benefit"]["benefit_status"] == "quantified"
