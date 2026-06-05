from __future__ import annotations

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


class ApiResponse(BaseModel):
    data: Any

