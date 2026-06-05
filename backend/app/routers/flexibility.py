from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import connect, init_database
from app.schemas import (
    FlexibilityBriefResponse,
    FlexibilityComputeCostResponse,
    FlexibilityEligibilityResponse,
    FlexibilityRulesResponse,
    FlexibilityScenarioRequest,
    FlexibilityTradeoffResponse,
)
from app.services.flexibility import (
    calculate_compute_cost,
    ensure_compute_assumption,
    evaluate_eligibility,
    generate_flexibility_brief,
    get_compute_assumption,
    list_flexibility_rules,
    run_tradeoff_sweep,
    seed_flexibility_rules,
)
from app.services.flexibility.scenario import store_scenario


router = APIRouter(prefix="/flexibility", tags=["flexibility"])


@router.get("/rules", response_model=FlexibilityRulesResponse)
def rules(jurisdiction: str | None = None) -> FlexibilityRulesResponse:
    seed_flexibility_rules()
    return FlexibilityRulesResponse(rules=list_flexibility_rules(jurisdiction=jurisdiction))


@router.post("/seed")
def seed() -> dict[str, Any]:
    return seed_flexibility_rules()


@router.post("/compute-cost", response_model=FlexibilityComputeCostResponse)
def compute_cost(request: FlexibilityScenarioRequest) -> FlexibilityComputeCostResponse:
    try:
        assumption = _assumption_from_request(request)
        return FlexibilityComputeCostResponse(
            compute_cost=calculate_compute_cost(
                peak_mw=request.peak_mw,
                commitment_depth_pct=request.commitment_depth_pct,
                event_duration_hours=request.event_duration_hours,
                events_per_year=request.events_per_year,
                assumption=assumption,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/eligibility", response_model=FlexibilityEligibilityResponse)
def eligibility(request: FlexibilityScenarioRequest) -> FlexibilityEligibilityResponse:
    try:
        assumption = _assumption_from_request(request)
        scenario = _store_request_scenario(request, assumption["assumption_id"])
        return FlexibilityEligibilityResponse(
            scenario=scenario,
            eligibility_results=evaluate_eligibility(scenario),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tradeoff", response_model=FlexibilityTradeoffResponse)
def tradeoff(request: FlexibilityScenarioRequest) -> FlexibilityTradeoffResponse:
    try:
        result = run_tradeoff_sweep(
            **_tradeoff_kwargs(request),
            assumption=_assumption_from_request(request),
        )
        return FlexibilityTradeoffResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/brief", response_model=FlexibilityBriefResponse)
def brief(request: FlexibilityScenarioRequest) -> FlexibilityBriefResponse:
    try:
        return FlexibilityBriefResponse(
            brief=generate_flexibility_brief(
                **_tradeoff_kwargs(request),
                commitment_depth_pct=request.commitment_depth_pct,
                assumption=_assumption_from_request(request),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scenarios/{scenario_id}")
def scenario(scenario_id: str) -> dict[str, Any]:
    init_database()
    with connect() as con:
        scenario_row = con.execute(
            """
            SELECT scenario_id, market, jurisdiction, county, peak_mw, average_load_factor,
                   commitment_depth_pct, event_duration_hours, events_per_year, job_mix_json,
                   colocated_generation, dispatchable_or_curtailable, metering_or_control_capability,
                   assumption_id, created_at
            FROM curtailment_scenarios
            WHERE scenario_id = ?
            """,
            [scenario_id],
        ).fetchone()
        if not scenario_row:
            raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
        tradeoffs = con.execute(
            """
            SELECT tradeoff_id, commitment_depth_pct, annual_curtailed_mwh, estimated_compute_cost_usd,
                   benefit_status, net_benefit_score, explanation
            FROM flexibility_tradeoff_points
            WHERE scenario_id = ?
            ORDER BY commitment_depth_pct
            """,
            [scenario_id],
        ).fetchall()
    return {
        "scenario": {
            "scenario_id": scenario_row[0],
            "market": scenario_row[1],
            "jurisdiction": scenario_row[2],
            "county": scenario_row[3],
            "peak_mw": scenario_row[4],
            "average_load_factor": scenario_row[5],
            "commitment_depth_pct": scenario_row[6],
            "event_duration_hours": scenario_row[7],
            "events_per_year": scenario_row[8],
            "job_mix_json": _json(scenario_row[9]),
            "colocated_generation": scenario_row[10],
            "dispatchable_or_curtailable": scenario_row[11],
            "metering_or_control_capability": scenario_row[12],
            "assumption_id": scenario_row[13],
            "created_at": scenario_row[14].isoformat() if hasattr(scenario_row[14], "isoformat") else scenario_row[14],
        },
        "tradeoff_points": [
            {
                "tradeoff_id": row[0],
                "commitment_depth_pct": row[1],
                "annual_curtailed_mwh": row[2],
                "estimated_compute_cost_usd": row[3],
                "benefit_status": row[4],
                "net_benefit_score": row[5],
                "explanation": row[6],
            }
            for row in tradeoffs
        ],
    }


def _tradeoff_kwargs(request: FlexibilityScenarioRequest) -> dict[str, Any]:
    return {
        "market": request.market,
        "jurisdiction": request.jurisdiction,
        "county": request.county,
        "peak_mw": request.peak_mw,
        "average_load_factor": request.average_load_factor,
        "event_duration_hours": request.event_duration_hours,
        "events_per_year": request.events_per_year,
        "job_mix_json": _job_mix(request),
        "colocated_generation": request.colocated_generation,
        "dispatchable_or_curtailable": request.dispatchable_or_curtailable,
        "metering_or_control_capability": request.metering_or_control_capability,
        "baseline_project_type": request.baseline_project_type,
        "min_sample_n": request.min_sample_n,
        "value_per_day_usd": request.value_per_day_usd,
    }


def _store_request_scenario(request: FlexibilityScenarioRequest, assumption_id: str) -> dict[str, Any]:
    return store_scenario(
        market=request.market,
        jurisdiction=request.jurisdiction,
        county=request.county,
        peak_mw=request.peak_mw,
        average_load_factor=request.average_load_factor,
        commitment_depth_pct=request.commitment_depth_pct,
        event_duration_hours=request.event_duration_hours,
        events_per_year=request.events_per_year,
        job_mix_json=_job_mix(request),
        colocated_generation=request.colocated_generation,
        dispatchable_or_curtailable=request.dispatchable_or_curtailable,
        metering_or_control_capability=request.metering_or_control_capability,
        assumption_id=assumption_id,
    )


def _assumption_from_request(request: FlexibilityScenarioRequest) -> dict[str, Any]:
    seed_flexibility_rules()
    if request.assumption_id:
        return get_compute_assumption(request.assumption_id)
    return ensure_compute_assumption(
        assumption_name="API scenario assumptions",
        peak_mw=request.peak_mw,
        average_load_factor=request.average_load_factor,
        deferrable_workload_fraction=request.deferrable_workload_fraction,
        latency_sensitive_fraction=request.latency_sensitive_fraction,
        migratable_fraction=request.migratable_fraction,
        gpu_power_kw=request.gpu_power_kw,
        gpu_hour_value_usd=request.gpu_hour_value_usd,
        deferral_penalty_per_gpu_hour_usd=request.deferral_penalty_per_gpu_hour_usd,
        migration_penalty_per_gpu_hour_usd=request.migration_penalty_per_gpu_hour_usd,
        dropped_work_penalty_per_gpu_hour_usd=request.dropped_work_penalty_per_gpu_hour_usd,
        default_event_duration_hours=request.event_duration_hours,
        default_events_per_year=request.events_per_year,
        evidence_anchor_json={
            "source_id": "src_emerald_epri_dcflex_arxiv_2507",
            "source_url": "https://arxiv.org/html/2507.00909v1",
            "field_demo_commitment_depth_pct": 25,
            "field_demo_event_duration_hours": 3,
        },
        notes="Assumptions supplied through the flexibility API request.",
    )


def _job_mix(request: FlexibilityScenarioRequest) -> dict[str, Any]:
    return {
        "deferrable_workload_fraction": request.deferrable_workload_fraction,
        "latency_sensitive_fraction": request.latency_sensitive_fraction,
        "migratable_fraction": request.migratable_fraction,
    }


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
