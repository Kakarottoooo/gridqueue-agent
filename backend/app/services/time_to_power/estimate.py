from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.time_to_power.equipment_scope import generate_equipment_scope
from app.services.time_to_power.fixtures import ensure_commissioning_assumption, seed_time_to_power_fixtures
from app.services.time_to_power.flex_adjusted import calculate_flex_adjusted_interconnection
from app.services.time_to_power.interconnection_baseline import get_interconnection_baseline
from app.services.time_to_power.procurement_critical_path import compute_procurement_critical_path
from app.services.time_to_power.scenario import create_time_to_power_scenario
from app.services.utils import new_id, stable_json, utcnow


def generate_time_to_power_estimate(
    *,
    scenario_name: str = "Fixture Time-to-Power Scenario",
    market: str = "ERCOT",
    jurisdiction: str = "FERC",
    county: str | None = "Reeves",
    region: str | None = None,
    project_type: str = "AI data center load",
    peak_mw: float = 300,
    average_load_factor: float = 0.85,
    interconnection_voltage_kv: float | None = 345,
    target_online_year: int | None = 2029,
    target_online_date: str | None = None,
    commitment_depth_pct: float = 20,
    event_duration_hours: float = 3,
    events_per_year: int = 20,
    procurement_strategy: str = "post_ntp_serial",
    equipment_scope_mode: str = "generated_planning_model",
    manual_equipment_scope_json: list[dict[str, Any]] | dict[str, Any] | None = None,
    min_sample_n: int = 2,
    stale_threshold_months: int = 18,
    commissioning_low_days: float | None = None,
    commissioning_high_days: float | None = None,
    energization_buffer_low_days: float | None = None,
    energization_buffer_high_days: float | None = None,
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
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_database(db_path)
    seed_time_to_power_fixtures(reset_core=False, db_path=db_path)
    scenario = create_time_to_power_scenario(
        scenario_name=scenario_name,
        market=market,
        jurisdiction=jurisdiction,
        county=county,
        region=region,
        project_type=project_type,
        peak_mw=peak_mw,
        average_load_factor=average_load_factor,
        interconnection_voltage_kv=interconnection_voltage_kv,
        target_online_year=target_online_year,
        target_online_date=target_online_date,
        procurement_strategy=procurement_strategy,
        equipment_scope_mode=equipment_scope_mode,
        manual_equipment_scope_json=manual_equipment_scope_json,
        db_path=db_path,
    )
    baseline = get_interconnection_baseline(
        market=market,
        county=county,
        project_type=project_type,
        peak_mw=peak_mw,
        target_online_year=target_online_year,
        min_sample_n=min_sample_n,
        db_path=db_path,
    )
    scope = generate_equipment_scope(
        project_type=project_type,
        peak_mw=peak_mw,
        interconnection_voltage_kv=interconnection_voltage_kv,
        manual_equipment_scope_json=manual_equipment_scope_json,
        equipment_scope_mode=equipment_scope_mode,
    )
    critical_path = compute_procurement_critical_path(
        scenario_id=scenario["scenario_id"],
        equipment_scope=scope,
        stale_threshold_months=stale_threshold_months,
        db_path=db_path,
    )
    commissioning = ensure_commissioning_assumption(
        commissioning_low_days=commissioning_low_days,
        commissioning_high_days=commissioning_high_days,
        energization_buffer_low_days=energization_buffer_low_days,
        energization_buffer_high_days=energization_buffer_high_days,
        db_path=db_path,
    )
    flex = calculate_flex_adjusted_interconnection(
        market=market,
        jurisdiction=jurisdiction,
        county=county,
        peak_mw=peak_mw,
        average_load_factor=average_load_factor,
        commitment_depth_pct=commitment_depth_pct,
        event_duration_hours=event_duration_hours,
        events_per_year=events_per_year,
        baseline=baseline,
        deferrable_workload_fraction=deferrable_workload_fraction,
        latency_sensitive_fraction=latency_sensitive_fraction,
        migratable_fraction=migratable_fraction,
        gpu_power_kw=gpu_power_kw,
        gpu_hour_value_usd=gpu_hour_value_usd,
        deferral_penalty_per_gpu_hour_usd=deferral_penalty_per_gpu_hour_usd,
        migration_penalty_per_gpu_hour_usd=migration_penalty_per_gpu_hour_usd,
        dropped_work_penalty_per_gpu_hour_usd=dropped_work_penalty_per_gpu_hour_usd,
        colocated_generation=colocated_generation,
        dispatchable_or_curtailable=dispatchable_or_curtailable,
        metering_or_control_capability=metering_or_control_capability,
        baseline_project_type=baseline["assumptions"].get("baseline_project_type", "Battery"),
        min_sample_n=min_sample_n,
        db_path=db_path,
    )
    timelines = _timeline_math(baseline, flex, critical_path, commissioning)
    status, status_explanation = _status(baseline, critical_path)
    selected_case = _selected_case(procurement_strategy, flex)
    binding_constraint = _binding_constraint(procurement_strategy, baseline, critical_path, commissioning)
    confidence = _confidence([baseline.get("confidence"), critical_path.get("confidence"), commissioning.get("confidence")])
    citations = _dedupe_citations(baseline.get("citations", []) + critical_path.get("citations", []) + flex.get("citations", []) + [_commissioning_citation(commissioning)])
    assumptions = {
        "serial_formula": "interconnection + procurement + commissioning + energization_buffer",
        "overlap_formula": "max(interconnection, procurement) + commissioning + energization_buffer",
        "procurement_strategy": procurement_strategy,
        "baseline_assumptions": baseline.get("assumptions", {}),
        "procurement_assumptions": critical_path.get("assumptions", {}),
        "commissioning_assumption": commissioning,
        "flexibility_assumptions": flex.get("assumptions", {}),
    }
    reproducibility_trace = [
        f"scenario_id={scenario['scenario_id']}",
        f"baseline_metric_id={baseline.get('metric_id')}, sample_n={baseline.get('sample_n')}, fallback_level={baseline.get('fallback_level')}, confidence={baseline.get('confidence')}",
        f"critical_path_id={critical_path['critical_path_id']}, binding_equipment_class={critical_path.get('binding_equipment_class')}",
        f"flexibility_status: rule_status={flex.get('rule_status')}, benefit_status={flex.get('benefit_status')}",
        "timeline_math: ranges are computed in days; lead-time months use days_per_month=30.4375.",
    ]
    estimate = {
        "estimate_id": new_id("ttp_est"),
        "scenario": scenario,
        "baseline": baseline,
        "equipment_scope": scope,
        "procurement_critical_path": critical_path,
        "flexibility_adjusted": flex,
        "commissioning_assumption": commissioning,
        **timelines,
        "selected_case": selected_case,
        "binding_constraint": binding_constraint,
        "confidence": confidence,
        "status": status,
        "status_explanation": status_explanation,
        "citations": citations,
        "assumptions": assumptions,
        "caveats": _caveats(procurement_strategy, baseline, critical_path, flex, scope),
        "reproducibility_trace": reproducibility_trace,
    }
    _store_components(estimate, db_path)
    _store_estimate(estimate, db_path)
    return estimate


def _timeline_math(
    baseline: dict[str, Any],
    flex: dict[str, Any],
    critical_path: dict[str, Any],
    commissioning: dict[str, Any],
) -> dict[str, Any]:
    base_low = baseline.get("baseline_low_days")
    base_high = baseline.get("baseline_high_days")
    proc_low = critical_path.get("procurement_low_days")
    proc_high = critical_path.get("procurement_high_days")
    comm_low = float(commissioning["default_commissioning_low_days"])
    comm_high = float(commissioning["default_commissioning_high_days"])
    buffer_low = float(commissioning["energization_buffer_low_days"])
    buffer_high = float(commissioning["energization_buffer_high_days"])
    flex_low = flex.get("interconnection_with_flex_low_days")
    flex_high = flex.get("interconnection_with_flex_high_days")
    return {
        "no_flex_serial_low_days": _sum(base_low, proc_low, comm_low, buffer_low),
        "no_flex_serial_high_days": _sum(base_high, proc_high, comm_high, buffer_high),
        "flex_serial_low_days": _sum(flex_low, proc_low, comm_low, buffer_low) if flex_low is not None else None,
        "flex_serial_high_days": _sum(flex_high, proc_high, comm_high, buffer_high) if flex_high is not None else None,
        "no_flex_overlap_low_days": _overlap(base_low, proc_low, comm_low, buffer_low),
        "no_flex_overlap_high_days": _overlap(base_high, proc_high, comm_high, buffer_high),
        "flex_overlap_low_days": _overlap(flex_low, proc_low, comm_low, buffer_low) if flex_low is not None else None,
        "flex_overlap_high_days": _overlap(flex_high, proc_high, comm_high, buffer_high) if flex_high is not None else None,
    }


def _sum(*values: float | None) -> float | None:
    if any(value is None for value in values):
        return None
    return round(sum(float(value) for value in values), 2)


def _overlap(interconnection: float | None, procurement: float | None, commissioning: float, buffer: float) -> float | None:
    if interconnection is None or procurement is None:
        return None
    return round(max(float(interconnection), float(procurement)) + commissioning + buffer, 2)


def _status(baseline: dict[str, Any], critical_path: dict[str, Any]) -> tuple[str, str]:
    if baseline.get("status") != "complete":
        return "insufficient_interconnection_baseline", "No sufficient GridQueue baseline duration proxy is available."
    if critical_path.get("unsupported_flag"):
        return "insufficient_procurement_data", "No supported lead-time rows matched the equipment scope."
    if critical_path.get("conflict_flag"):
        return "conflicting_procurement_data", "Lead-time sources conflict; ranges are preserved and flagged."
    if critical_path.get("stale_flag"):
        return "stale_procurement_data", "One or more public lead-time rows are stale and require manual review."
    return "complete", "All required components produced caveated ranges."


def _selected_case(strategy: str, flex: dict[str, Any]) -> str:
    has_quantified_flex = flex.get("benefit_status") == "quantified"
    if strategy == "at_risk_overlap":
        return "flex_overlap" if has_quantified_flex else "no_flex_overlap"
    return "flex_serial" if has_quantified_flex else "no_flex_serial"


def _binding_constraint(strategy: str, baseline: dict[str, Any], critical_path: dict[str, Any], commissioning: dict[str, Any]) -> str:
    base_high = baseline.get("baseline_high_days") or 0
    proc_high = critical_path.get("procurement_high_days") or 0
    comm_high = float(commissioning["default_commissioning_high_days"]) + float(commissioning["energization_buffer_high_days"])
    if strategy == "at_risk_overlap":
        return "procurement" if proc_high >= base_high else "interconnection"
    values = {"interconnection": base_high, "procurement": proc_high, "commissioning_and_buffer": comm_high}
    return max(values, key=values.get)


def _confidence(values: list[Any]) -> str:
    ranks = {"high": 3, "High": 3, "medium": 2, "Medium": 2, "low": 1, "Low": 1, "insufficient": 0, "Insufficient": 0}
    lowest = min((ranks.get(value, 1) for value in values if value is not None), default=0)
    return {3: "high", 2: "medium", 1: "low", 0: "insufficient"}[lowest]


def _commissioning_citation(commissioning: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation_label": "Commissioning and energization buffer assumption",
        "citation_text": f"{commissioning['default_commissioning_low_days']}-{commissioning['default_commissioning_high_days']} commissioning days plus {commissioning['energization_buffer_low_days']}-{commissioning['energization_buffer_high_days']} buffer days.",
        "source_url": commissioning["source_url"],
        "source_type": commissioning["source_type"],
        "as_of_date": commissioning["as_of_date"],
    }


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for citation in citations:
        key = f"{citation.get('citation_label')}|{citation.get('source_url')}|{citation.get('lead_time_id')}"
        if key not in seen:
            seen.add(key)
            result.append(citation)
    return result


def _caveats(
    strategy: str,
    baseline: dict[str, Any],
    critical_path: dict[str, Any],
    flex: dict[str, Any],
    scope: dict[str, Any],
) -> list[str]:
    caveats = [
        "This Time-to-Power estimate is a public-data planning artifact, not a formal study, procurement quote, engineering design, or guarantee.",
        *baseline.get("caveats", []),
        *critical_path.get("caveats", []),
        *flex.get("caveats", []),
        *scope.get("caveats", []),
    ]
    if strategy == "at_risk_overlap":
        caveats.append("At-risk overlap assumes procurement starts before final NTP; this can strand spend if interconnection outcomes change.")
    return list(dict.fromkeys(caveats))


def _store_components(estimate: dict[str, Any], db_path: str | Path | None) -> None:
    scenario_id = estimate["scenario"]["scenario_id"]
    components = [
        ("interconnection_baseline", "No-flex interconnection baseline", estimate["baseline"].get("baseline_low_days"), estimate["baseline"].get("baseline_high_days"), estimate["baseline"], "metric_rollup"),
        ("flexibility_adjustment", "Flexibility adjustment", estimate["flexibility_adjusted"].get("flex_adjustment_low_days"), estimate["flexibility_adjusted"].get("flex_adjustment_high_days"), estimate["flexibility_adjusted"], "flexibility_rule"),
        ("interconnection_with_flex", "Interconnection with flexibility", estimate["flexibility_adjusted"].get("interconnection_with_flex_low_days"), estimate["flexibility_adjusted"].get("interconnection_with_flex_high_days"), estimate["flexibility_adjusted"], "flexibility_rule"),
        ("procurement_critical_path", "Procurement critical path", estimate["procurement_critical_path"].get("procurement_low_days"), estimate["procurement_critical_path"].get("procurement_high_days"), estimate["procurement_critical_path"], "equipment_lead_times"),
        ("commissioning", "Commissioning", estimate["commissioning_assumption"].get("default_commissioning_low_days"), estimate["commissioning_assumption"].get("default_commissioning_high_days"), estimate["commissioning_assumption"], "commissioning_assumption"),
        ("energization_buffer", "Energization buffer", estimate["commissioning_assumption"].get("energization_buffer_low_days"), estimate["commissioning_assumption"].get("energization_buffer_high_days"), estimate["commissioning_assumption"], "commissioning_assumption"),
        ("total_serial", "No-flex serial total", estimate.get("no_flex_serial_low_days"), estimate.get("no_flex_serial_high_days"), estimate, "calculation"),
        ("total_overlap", "No-flex overlap total", estimate.get("no_flex_overlap_low_days"), estimate.get("no_flex_overlap_high_days"), estimate, "calculation"),
    ]
    with connect(db_path) as con:
        for component_type, name, low, high, source, source_type in components:
            con.execute(
                """
                INSERT INTO time_to_power_components
                (component_id, scenario_id, component_type, component_name, low_days, high_days, confidence,
                 source_type, source_id, source_url, citation_ids_json, assumptions_json, caveats_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    new_id("ttp_comp"),
                    scenario_id,
                    component_type,
                    name,
                    low,
                    high,
                    source.get("confidence", estimate.get("confidence", "low")) if isinstance(source, dict) else "low",
                    source_type,
                    source.get("metric_id") or source.get("critical_path_id") or source.get("commissioning_assumption_id") if isinstance(source, dict) else None,
                    _first_source_url(source),
                    stable_json([citation.get("citation_label") for citation in estimate["citations"] if citation.get("source_url") == _first_source_url(source)]),
                    stable_json(source.get("assumptions", source) if isinstance(source, dict) else {}),
                    stable_json(source.get("caveats", []) if isinstance(source, dict) else []),
                    utcnow(),
                ],
            )


def _first_source_url(source: dict[str, Any]) -> str | None:
    if not isinstance(source, dict):
        return None
    if source.get("source_url"):
        return source["source_url"]
    citations = source.get("citations") or []
    return citations[0].get("source_url") if citations else None


def _store_estimate(estimate: dict[str, Any], db_path: str | Path | None) -> None:
    with connect(db_path) as con:
        con.execute(
            """
            INSERT INTO time_to_power_estimates
            (estimate_id, scenario_id, baseline_metric_id, flexibility_tradeoff_id, critical_path_id,
             commissioning_assumption_id, no_flex_serial_low_days, no_flex_serial_high_days,
             flex_serial_low_days, flex_serial_high_days, no_flex_overlap_low_days, no_flex_overlap_high_days,
             flex_overlap_low_days, flex_overlap_high_days, selected_case, binding_constraint,
             confidence, status, status_explanation, citations_json, assumptions_json,
             reproducibility_trace_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                estimate["estimate_id"],
                estimate["scenario"]["scenario_id"],
                estimate["baseline"].get("metric_id"),
                estimate["scenario"].get("selected_tradeoff_id"),
                estimate["procurement_critical_path"].get("critical_path_id"),
                estimate["commissioning_assumption"].get("commissioning_assumption_id"),
                estimate.get("no_flex_serial_low_days"),
                estimate.get("no_flex_serial_high_days"),
                estimate.get("flex_serial_low_days"),
                estimate.get("flex_serial_high_days"),
                estimate.get("no_flex_overlap_low_days"),
                estimate.get("no_flex_overlap_high_days"),
                estimate.get("flex_overlap_low_days"),
                estimate.get("flex_overlap_high_days"),
                estimate["selected_case"],
                estimate["binding_constraint"],
                estimate["confidence"],
                estimate["status"],
                estimate["status_explanation"],
                stable_json(estimate["citations"]),
                stable_json(estimate["assumptions"]),
                stable_json(estimate["reproducibility_trace"]),
                utcnow(),
            ],
        )
