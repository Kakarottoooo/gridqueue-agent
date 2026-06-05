from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.flexibility import calculate_compute_cost, ensure_compute_assumption, estimate_interconnection_benefit, evaluate_eligibility, seed_flexibility_rules
from app.services.flexibility.scenario import store_scenario


def calculate_flex_adjusted_interconnection(
    *,
    market: str,
    jurisdiction: str,
    county: str | None,
    peak_mw: float,
    average_load_factor: float,
    commitment_depth_pct: float,
    event_duration_hours: float,
    events_per_year: int,
    baseline: dict[str, Any],
    deferrable_workload_fraction: float = 0.55,
    latency_sensitive_fraction: float = 0.25,
    migratable_fraction: float = 0.20,
    gpu_power_kw: float = 0.7,
    gpu_hour_value_usd: float = 3.0,
    deferral_penalty_per_gpu_hour_usd: float = 0.25,
    migration_penalty_per_gpu_hour_usd: float = 0.75,
    dropped_work_penalty_per_gpu_hour_usd: float = 4.0,
    colocated_generation: bool = False,
    dispatchable_or_curtailable: bool | None = True,
    metering_or_control_capability: bool | None = True,
    baseline_project_type: str = "Battery",
    min_sample_n: int = 30,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    seed_flexibility_rules(db_path)
    assumption = ensure_compute_assumption(
        assumption_name="Time-to-Power flexibility assumptions",
        peak_mw=peak_mw,
        average_load_factor=average_load_factor,
        deferrable_workload_fraction=deferrable_workload_fraction,
        latency_sensitive_fraction=latency_sensitive_fraction,
        migratable_fraction=migratable_fraction,
        gpu_power_kw=gpu_power_kw,
        gpu_hour_value_usd=gpu_hour_value_usd,
        deferral_penalty_per_gpu_hour_usd=deferral_penalty_per_gpu_hour_usd,
        migration_penalty_per_gpu_hour_usd=migration_penalty_per_gpu_hour_usd,
        dropped_work_penalty_per_gpu_hour_usd=dropped_work_penalty_per_gpu_hour_usd,
        default_event_duration_hours=event_duration_hours,
        default_events_per_year=events_per_year,
        evidence_anchor_json={
            "source_id": "src_emerald_epri_dcflex_arxiv_2507",
            "source_url": "https://arxiv.org/html/2507.00909v1",
            "field_demo_commitment_depth_pct": 25,
            "field_demo_event_duration_hours": 3,
        },
        notes="Time-to-Power API request assumptions.",
        db_path=db_path,
    )
    scenario = store_scenario(
        market=market,
        jurisdiction=jurisdiction,
        county=county,
        peak_mw=peak_mw,
        average_load_factor=average_load_factor,
        commitment_depth_pct=commitment_depth_pct,
        event_duration_hours=event_duration_hours,
        events_per_year=events_per_year,
        job_mix_json={
            "deferrable_workload_fraction": deferrable_workload_fraction,
            "latency_sensitive_fraction": latency_sensitive_fraction,
            "migratable_fraction": migratable_fraction,
        },
        colocated_generation=colocated_generation,
        dispatchable_or_curtailable=dispatchable_or_curtailable,
        metering_or_control_capability=metering_or_control_capability,
        assumption_id=assumption["assumption_id"],
        db_path=db_path,
    )
    compute = calculate_compute_cost(
        peak_mw=peak_mw,
        commitment_depth_pct=commitment_depth_pct,
        event_duration_hours=event_duration_hours,
        events_per_year=events_per_year,
        assumption=assumption,
    )
    eligibility = evaluate_eligibility(scenario, db_path=db_path, persist=True)
    benefit = estimate_interconnection_benefit(
        scenario,
        eligibility,
        baseline_project_type=baseline_project_type,
        min_sample_n=min_sample_n,
        db_path=db_path,
    )
    benefit_status = benefit["benefit_status"]
    delta = benefit.get("estimated_timeline_delta_days")
    if benefit_status == "quantified" and delta is not None and baseline.get("baseline_low_days") is not None:
        flex_low = max(0.0, float(baseline["baseline_low_days"]) - float(delta))
        flex_high = max(flex_low, float(baseline["baseline_high_days"]) - float(delta))
        adjustment_low = -float(delta)
        adjustment_high = -float(delta)
    else:
        flex_low = None
        flex_high = None
        adjustment_low = None
        adjustment_high = None

    citations = _dedupe_citations(
        [
            citation
            for result in eligibility
            for citation in result.get("citations", [])
        ]
        + [{"citation_label": "Compute flexibility evidence anchor", "source_url": assumption["evidence_anchor_json"].get("source_url"), "citation_text": "Technical evidence anchor; not a regulatory rule."}]
    )
    return {
        "scenario_id": scenario["scenario_id"],
        "eligibility_status": eligibility[0]["eligibility_status"] if eligibility else "unsupported",
        "benefit_status": benefit_status,
        "rule_status": benefit.get("rule_status") or (eligibility[0]["rule_status"] if eligibility else None),
        "rule_id": benefit.get("rule_id"),
        "compute_cost_summary": compute,
        "eligibility_results": eligibility,
        "flex_adjustment_low_days": adjustment_low,
        "flex_adjustment_high_days": adjustment_high,
        "interconnection_with_flex_low_days": flex_low,
        "interconnection_with_flex_high_days": flex_high,
        "citations": citations,
        "assumptions": {"compute_cost_assumption": assumption, "baseline_project_type": baseline_project_type, "min_sample_n": min_sample_n},
        "caveats": _caveats(benefit_status, benefit.get("rule_status"), eligibility),
    }


def _caveats(benefit_status: str, rule_status: str | None, eligibility: list[dict[str, Any]]) -> list[str]:
    caveats = ["Flexibility does not reduce procurement lead time by default."]
    if benefit_status != "quantified":
        caveats.append("No quantified day-saved timeline math is applied because the flexibility evidence is contingent, qualitative-only, unsupported, or insufficient.")
    if rule_status and rule_status not in {"approved", "final"}:
        caveats.append(f"Rule status is {rule_status}; proposed or pending benefits remain contingent and are not treated as final.")
    if any(result.get("rule_status") == "technical_evidence" for result in eligibility):
        caveats.append("Technical evidence is treated as compute-context evidence, not as regulation.")
    return caveats


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for citation in citations:
        source_url = citation.get("source_url")
        if source_url and source_url not in seen:
            seen.add(source_url)
            result.append(citation)
    return result
