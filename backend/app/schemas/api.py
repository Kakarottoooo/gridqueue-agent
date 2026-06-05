from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class DiffRequest(BaseModel):
    market: str = "ERCOT"
    from_snapshot_id: str
    to_snapshot_id: str


class MetricsRequest(BaseModel):
    market: str = "ERCOT"
    county: str | None = None
    fuel_type: str | None = Field(default=None, examples=["Battery"])
    min_sample_n: int = Field(default=30, ge=1)


class BriefRequest(BaseModel):
    market: str = "ERCOT"
    project_type: str = "Battery"
    county: str | None = "Reeves"
    capacity_mw: float | None = 100
    target_cod_year: int | None = 2028
    question: str | None = "What public interconnection risks should I know?"
    min_sample_n: int = Field(default=30, ge=1)


class IngestManualRequest(BaseModel):
    local_path: str | None = None
    market: str = "ERCOT"
    source_kind: Literal["ercot", "lbnl"] = "ercot"


class FlexibilityScenarioRequest(BaseModel):
    market: str = "ERCOT"
    jurisdiction: str = "FERC"
    county: str | None = "Reeves"
    peak_mw: float = Field(default=100, gt=0)
    average_load_factor: float = Field(default=0.85, ge=0, le=1)
    commitment_depth_pct: float = Field(default=25, ge=0, le=100)
    event_duration_hours: float = Field(default=3, gt=0)
    events_per_year: int = Field(default=20, ge=0)
    deferrable_workload_fraction: float = Field(default=0.55, ge=0, le=1)
    latency_sensitive_fraction: float = Field(default=0.25, ge=0, le=1)
    migratable_fraction: float = Field(default=0.20, ge=0, le=1)
    gpu_power_kw: float = Field(default=0.7, gt=0)
    gpu_hour_value_usd: float = Field(default=3.0, ge=0)
    deferral_penalty_per_gpu_hour_usd: float = Field(default=0.25, ge=0)
    migration_penalty_per_gpu_hour_usd: float = Field(default=0.75, ge=0)
    dropped_work_penalty_per_gpu_hour_usd: float = Field(default=4.0, ge=0)
    colocated_generation: bool = False
    dispatchable_or_curtailable: bool | None = True
    metering_or_control_capability: bool | None = True
    baseline_project_type: str = "Battery"
    min_sample_n: int = Field(default=2, ge=1)
    value_per_day_usd: float | None = Field(default=None, ge=0)
    assumption_id: str | None = None


class FlexibilityComputeCostResponse(BaseModel):
    compute_cost: dict[str, Any]


class FlexibilityRulesResponse(BaseModel):
    rules: list[dict[str, Any]]


class FlexibilityEligibilityResponse(BaseModel):
    scenario: dict[str, Any]
    eligibility_results: list[dict[str, Any]]


class FlexibilityTradeoffResponse(BaseModel):
    scenario: dict[str, Any]
    assumption: dict[str, Any]
    tradeoff_points: list[dict[str, Any]]
    recommendation: dict[str, Any]


class FlexibilityBriefResponse(BaseModel):
    brief: dict[str, Any]


class WatcherRunRequest(BaseModel):
    mode: Literal["fixture", "manual", "live"] = "fixture"
    period_start: date = date(2026, 5, 1)
    period_end: date = date(2026, 5, 31)
    market: str = "ERCOT"
    from_snapshot_id: str | None = None
    to_snapshot_id: str | None = None
    top_n: int = Field(default=10, ge=1, le=50)


class WatcherQueueAdapterRequest(BaseModel):
    market: str = "ERCOT"
    from_snapshot_id: str
    to_snapshot_id: str


class WatcherRegulatorySnapshotRequest(BaseModel):
    mode: Literal["fixture", "manual", "live"] = "fixture"
    fixture_variant: str = "current"


class WatcherDigestRequest(BaseModel):
    period_start: date = date(2026, 5, 1)
    period_end: date = date(2026, 5, 31)
    top_n: int = Field(default=10, ge=1, le=50)


class WatcherSourcesResponse(BaseModel):
    sources: list[dict[str, Any]]


class WatcherChangeEventsResponse(BaseModel):
    change_events: list[dict[str, Any]]


class WatcherDigestsResponse(BaseModel):
    digests: list[dict[str, Any]]


class ProcurementLeadTimesResponse(BaseModel):
    lead_times: list[dict[str, Any]]


class ApiResponse(BaseModel):
    data: Any
