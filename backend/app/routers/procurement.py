from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.schemas import ProcurementLeadTimesResponse
from app.services.procurement import list_lead_times, seed_lead_time_kb


router = APIRouter(prefix="/procurement", tags=["procurement"])


@router.post("/lead-times/seed")
def seed_lead_times() -> dict[str, Any]:
    return seed_lead_time_kb()


@router.get("/lead-times", response_model=ProcurementLeadTimesResponse)
def lead_times(equipment_class: str | None = None) -> ProcurementLeadTimesResponse:
    return ProcurementLeadTimesResponse(lead_times=list_lead_times(equipment_class=equipment_class))
