from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.flexibility.benefit import estimate_interconnection_benefit
from app.services.flexibility.compute_cost import calculate_compute_cost
from app.services.flexibility.eligibility import evaluate_eligibility
from app.services.flexibility.scenario import store_scenario
from app.services.flexibility.seed import seed_flexibility_rules
from app.services.utils import new_id, utcnow


DEFAULT_COMMITMENT_LEVELS = (0, 5, 10, 15, 20, 25, 30, 40, 50)


def run_tradeoff_sweep(
    *,
    market: str,
    jurisdiction: str,
    county: str | None,
    peak_mw: float,
    average_load_factor: float,
    event_duration_hours: float,
    events_per_year: int,
    job_mix_json: dict[str, Any],
    colocated_generation: bool,
    dispatchable_or_curtailable: bool | None,
    metering_or_control_capability: bool | None,
    assumption: dict[str, Any],
    baseline_project_type: str = "Battery",
    min_sample_n: int = 30,
    value_per_day_usd: float | None = None,
    commitment_levels: list[float] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    seed_flexibility_rules(db_path)
    levels = commitment_levels or list(DEFAULT_COMMITMENT_LEVELS)
    scenario = store_scenario(
        market=market,
        jurisdiction=jurisdiction,
        county=county,
        peak_mw=peak_mw,
        average_load_factor=average_load_factor,
        commitment_depth_pct=levels[0],
        event_duration_hours=event_duration_hours,
        events_per_year=events_per_year,
        job_mix_json=job_mix_json,
        colocated_generation=colocated_generation,
        dispatchable_or_curtailable=dispatchable_or_curtailable,
        metering_or_control_capability=metering_or_control_capability,
        assumption_id=assumption["assumption_id"],
        db_path=db_path,
    )
    points = []
    with connect(db_path) as con:
        for level in levels:
            point_scenario = {**scenario, "commitment_depth_pct": float(level)}
            compute = calculate_compute_cost(
                peak_mw=peak_mw,
                commitment_depth_pct=float(level),
                event_duration_hours=event_duration_hours,
                events_per_year=events_per_year,
                assumption=assumption,
            )
            eligibility = evaluate_eligibility(point_scenario, db_path=db_path, persist=False)
            benefit = estimate_interconnection_benefit(
                point_scenario,
                eligibility,
                baseline_project_type=baseline_project_type,
                min_sample_n=min_sample_n,
                db_path=db_path,
            )
            net_benefit_score = None
            if benefit["benefit_status"] == "quantified" and value_per_day_usd is not None:
                net_benefit_score = round(
                    float(benefit["estimated_timeline_delta_days"] or 0) * value_per_day_usd
                    - float(compute["estimated_compute_cost_usd"]),
                    2,
                )
            tradeoff_id = new_id("tradeoff")
            explanation = _point_explanation(benefit, net_benefit_score)
            con.execute(
                """
                INSERT INTO flexibility_tradeoff_points
                (tradeoff_id, scenario_id, commitment_depth_pct, annual_curtailed_mwh,
                 deferred_gpu_hours, migrated_gpu_hours, dropped_or_unserved_gpu_hours,
                 estimated_compute_cost_usd, baseline_timeline_days, baseline_metric_id,
                 baseline_sample_n, baseline_fallback_level, baseline_confidence,
                 with_flex_timeline_days, estimated_timeline_delta_days, benefit_status,
                 net_benefit_score, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    tradeoff_id,
                    scenario["scenario_id"],
                    float(level),
                    compute["annual_curtailed_mwh"],
                    compute["deferred_gpu_hours"],
                    compute["migrated_gpu_hours"],
                    compute["dropped_or_unserved_gpu_hours"],
                    compute["estimated_compute_cost_usd"],
                    benefit["baseline_timeline_days"],
                    benefit["baseline_metric_id"],
                    int(benefit["sample_n"] or 0),
                    benefit["fallback_level"] or "none",
                    benefit["confidence"] or "Insufficient",
                    benefit["with_flex_timeline_days"],
                    benefit["estimated_timeline_delta_days"],
                    benefit["benefit_status"],
                    net_benefit_score,
                    explanation,
                    utcnow(),
                ],
            )
            points.append(
                {
                    "tradeoff_id": tradeoff_id,
                    "scenario_id": scenario["scenario_id"],
                    "commitment_depth_pct": float(level),
                    "compute_cost": compute,
                    "eligibility_results": eligibility,
                    "benefit": benefit,
                    "net_benefit_score": net_benefit_score,
                    "explanation": explanation,
                }
            )
    recommendation = _recommend(points, value_per_day_usd)
    return {
        "scenario": scenario,
        "assumption": assumption,
        "value_per_day_usd": value_per_day_usd,
        "tradeoff_points": points,
        "recommendation": recommendation,
    }


def _point_explanation(benefit: dict[str, Any], net_benefit_score: float | None) -> str:
    if benefit["benefit_status"] == "quantified" and net_benefit_score is not None:
        return "Quantified fixture benefit and value-per-day assumption produced a net-benefit score."
    if benefit["benefit_status"] == "quantified":
        return "Quantified fixture benefit exists, but no value_per_day_usd was supplied for net scoring."
    return benefit["explanation"]


def _recommend(points: list[dict[str, Any]], value_per_day_usd: float | None) -> dict[str, Any]:
    scored = [point for point in points if point["net_benefit_score"] is not None]
    if not scored:
        return {
            "mode": "scenario_comparison_only",
            "selected_tradeoff_id": None,
            "message": "No hard recommendation because benefits are qualitative, contingent, unsupported, or missing value_per_day_usd.",
        }
    selected = max(scored, key=lambda point: point["net_benefit_score"])
    return {
        "mode": "max_net_benefit_under_assumptions",
        "selected_tradeoff_id": selected["tradeoff_id"],
        "commitment_depth_pct": selected["commitment_depth_pct"],
        "net_benefit_score": selected["net_benefit_score"],
        "value_per_day_usd": value_per_day_usd,
        "message": "Scenario-based recommendation under supplied assumptions; not a prediction or guarantee.",
    }
