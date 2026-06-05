from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import connect, init_database
from app.schemas import (
    TimeToPowerBaselineResponse,
    TimeToPowerBriefResponse,
    TimeToPowerCriticalPathResponse,
    TimeToPowerEquipmentScopeRequest,
    TimeToPowerEquipmentScopeResponse,
    TimeToPowerEstimateResponse,
    TimeToPowerFlexAdjustedResponse,
    TimeToPowerScenarioRequest,
    TimeToPowerScenarioResponse,
)
from app.services.time_to_power import (
    calculate_flex_adjusted_interconnection,
    compute_procurement_critical_path,
    create_time_to_power_scenario,
    generate_equipment_scope,
    generate_time_to_power_brief,
    generate_time_to_power_estimate,
    get_interconnection_baseline,
    get_time_to_power_brief,
    get_time_to_power_scenario,
    latest_time_to_power_brief,
    seed_time_to_power_fixtures,
)
from app.services.time_to_power.fixtures import ensure_commissioning_assumption


router = APIRouter(prefix="/time-to-power", tags=["time-to-power"])


@router.get("/health")
def health() -> dict[str, Any]:
    init_database()
    return {
        "status": "ok",
        "features": [
            "scenario_storage",
            "equipment_scope",
            "interconnection_baseline",
            "flex_adjusted",
            "procurement_critical_path",
            "estimate",
            "brief",
        ],
    }


@router.post("/fixtures/seed")
def seed_fixtures() -> dict[str, Any]:
    return seed_time_to_power_fixtures(reset_core=False)


@router.post("/scenarios", response_model=TimeToPowerScenarioResponse)
def create_scenario(request: TimeToPowerScenarioRequest) -> TimeToPowerScenarioResponse:
    return TimeToPowerScenarioResponse(scenario=create_time_to_power_scenario(**_scenario_kwargs(request)))


@router.get("/scenarios/{scenario_id}", response_model=TimeToPowerScenarioResponse)
def read_scenario(scenario_id: str) -> TimeToPowerScenarioResponse:
    scenario = get_time_to_power_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    return TimeToPowerScenarioResponse(scenario=scenario)


@router.post("/equipment-scope", response_model=TimeToPowerEquipmentScopeResponse)
def equipment_scope(request: TimeToPowerEquipmentScopeRequest) -> TimeToPowerEquipmentScopeResponse:
    return TimeToPowerEquipmentScopeResponse(
        equipment_scope=generate_equipment_scope(
            project_type=request.project_type,
            peak_mw=request.peak_mw,
            interconnection_voltage_kv=request.interconnection_voltage_kv,
            manual_equipment_scope_json=request.manual_equipment_scope_json,
            equipment_scope_mode=request.equipment_scope_mode,
        )
    )


@router.post("/procurement-critical-path", response_model=TimeToPowerCriticalPathResponse)
def procurement_critical_path(request: TimeToPowerScenarioRequest) -> TimeToPowerCriticalPathResponse:
    try:
        scenario = create_time_to_power_scenario(**_scenario_kwargs(request))
        scope = generate_equipment_scope(
            project_type=request.project_type,
            peak_mw=request.peak_mw,
            interconnection_voltage_kv=request.interconnection_voltage_kv,
            manual_equipment_scope_json=request.manual_equipment_scope_json,
            equipment_scope_mode=request.equipment_scope_mode,
        )
        return TimeToPowerCriticalPathResponse(
            critical_path=compute_procurement_critical_path(
                scenario_id=scenario["scenario_id"],
                equipment_scope=scope,
                stale_threshold_months=request.stale_threshold_months,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/interconnection-baseline", response_model=TimeToPowerBaselineResponse)
def interconnection_baseline(request: TimeToPowerScenarioRequest) -> TimeToPowerBaselineResponse:
    return TimeToPowerBaselineResponse(
        baseline=get_interconnection_baseline(
            market=request.market,
            county=request.county,
            project_type=request.project_type,
            peak_mw=request.peak_mw,
            target_online_year=request.target_online_year,
            min_sample_n=request.min_sample_n,
        )
    )


@router.post("/flex-adjusted", response_model=TimeToPowerFlexAdjustedResponse)
def flex_adjusted(request: TimeToPowerScenarioRequest) -> TimeToPowerFlexAdjustedResponse:
    baseline = get_interconnection_baseline(
        market=request.market,
        county=request.county,
        project_type=request.project_type,
        peak_mw=request.peak_mw,
        target_online_year=request.target_online_year,
        min_sample_n=request.min_sample_n,
    )
    return TimeToPowerFlexAdjustedResponse(
        flex_adjusted=calculate_flex_adjusted_interconnection(
            market=request.market,
            jurisdiction=request.jurisdiction,
            county=request.county,
            peak_mw=request.peak_mw,
            average_load_factor=request.average_load_factor,
            commitment_depth_pct=request.commitment_depth_pct,
            event_duration_hours=request.event_duration_hours,
            events_per_year=request.events_per_year,
            baseline=baseline,
            deferrable_workload_fraction=request.deferrable_workload_fraction,
            latency_sensitive_fraction=request.latency_sensitive_fraction,
            migratable_fraction=request.migratable_fraction,
            gpu_power_kw=request.gpu_power_kw,
            gpu_hour_value_usd=request.gpu_hour_value_usd,
            deferral_penalty_per_gpu_hour_usd=request.deferral_penalty_per_gpu_hour_usd,
            migration_penalty_per_gpu_hour_usd=request.migration_penalty_per_gpu_hour_usd,
            dropped_work_penalty_per_gpu_hour_usd=request.dropped_work_penalty_per_gpu_hour_usd,
            colocated_generation=request.colocated_generation,
            dispatchable_or_curtailable=request.dispatchable_or_curtailable,
            metering_or_control_capability=request.metering_or_control_capability,
            baseline_project_type=baseline["assumptions"].get("baseline_project_type", "Battery"),
            min_sample_n=request.min_sample_n,
        )
    )


@router.post("/estimate", response_model=TimeToPowerEstimateResponse)
def estimate(request: TimeToPowerScenarioRequest) -> TimeToPowerEstimateResponse:
    try:
        return TimeToPowerEstimateResponse(estimate=generate_time_to_power_estimate(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/brief", response_model=TimeToPowerBriefResponse)
def brief(request: TimeToPowerScenarioRequest) -> TimeToPowerBriefResponse:
    try:
        return TimeToPowerBriefResponse(brief=generate_time_to_power_brief(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/briefs/latest", response_model=TimeToPowerBriefResponse)
def latest_brief() -> TimeToPowerBriefResponse:
    brief_result = latest_time_to_power_brief()
    if not brief_result:
        raise HTTPException(status_code=404, detail="No Time-to-Power brief has been generated.")
    return TimeToPowerBriefResponse(brief=brief_result)


@router.get("/briefs/{brief_id}", response_model=TimeToPowerBriefResponse)
def read_brief(brief_id: str) -> TimeToPowerBriefResponse:
    brief_result = get_time_to_power_brief(brief_id)
    if not brief_result:
        raise HTTPException(status_code=404, detail=f"Time-to-Power brief not found: {brief_id}")
    return TimeToPowerBriefResponse(brief=brief_result)


@router.post("/demo", response_model=TimeToPowerBriefResponse)
def demo() -> TimeToPowerBriefResponse:
    seed_time_to_power_fixtures(reset_core=True)
    return TimeToPowerBriefResponse(brief=generate_time_to_power_brief())


def _scenario_kwargs(request: TimeToPowerScenarioRequest) -> dict[str, Any]:
    data = request.model_dump()
    allowed = {
        "scenario_name",
        "market",
        "jurisdiction",
        "county",
        "region",
        "project_type",
        "peak_mw",
        "average_load_factor",
        "interconnection_voltage_kv",
        "target_online_year",
        "target_online_date",
        "procurement_strategy",
        "equipment_scope_mode",
        "manual_equipment_scope_json",
    }
    return {key: data[key] for key in allowed}
