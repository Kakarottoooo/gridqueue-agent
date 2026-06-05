from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import (
    WatcherChangeEventsResponse,
    WatcherDigestRequest,
    WatcherDigestsResponse,
    WatcherQueueAdapterRequest,
    WatcherRegulatorySnapshotRequest,
    WatcherRunRequest,
    WatcherSourcesResponse,
)
from app.services.watcher import (
    adapt_queue_diff,
    capture_regulatory_snapshots,
    generate_monthly_digest,
    latest_digest,
    list_digests,
    list_watch_sources,
    run_monthly_watcher,
    seed_watch_sources,
)
from app.services.watcher.digest import list_change_events


router = APIRouter(prefix="/watcher", tags=["watcher"])


@router.get("/sources", response_model=WatcherSourcesResponse)
def sources() -> WatcherSourcesResponse:
    return WatcherSourcesResponse(sources=list_watch_sources())


@router.post("/sources/seed")
def seed_sources() -> dict[str, Any]:
    return seed_watch_sources()


@router.post("/run")
def run(request: WatcherRunRequest) -> dict[str, Any]:
    try:
        return run_monthly_watcher(
            mode=request.mode,
            period_start=request.period_start,
            period_end=request.period_end,
            market=request.market,
            from_snapshot_id=request.from_snapshot_id,
            to_snapshot_id=request.to_snapshot_id,
            top_n=request.top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/queue-adapter")
def queue_adapter(request: WatcherQueueAdapterRequest) -> dict[str, Any]:
    try:
        return adapt_queue_diff(
            market=request.market,
            from_snapshot_id=request.from_snapshot_id,
            to_snapshot_id=request.to_snapshot_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/regulatory-snapshot")
def regulatory_snapshot(request: WatcherRegulatorySnapshotRequest) -> dict[str, Any]:
    try:
        return capture_regulatory_snapshots(mode=request.mode, fixture_variant=request.fixture_variant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/digest")
def digest(request: WatcherDigestRequest) -> dict[str, Any]:
    return generate_monthly_digest(
        period_start=request.period_start,
        period_end=request.period_end,
        top_n=request.top_n,
    )


@router.get("/digests", response_model=WatcherDigestsResponse)
def digests() -> WatcherDigestsResponse:
    return WatcherDigestsResponse(digests=list_digests())


@router.get("/digests/latest")
def digest_latest() -> dict[str, Any]:
    digest = latest_digest()
    if not digest:
        raise HTTPException(status_code=404, detail="No monthly watcher digest has been generated.")
    return digest


@router.get("/change-events", response_model=WatcherChangeEventsResponse)
def change_events(event_domain: str | None = None) -> WatcherChangeEventsResponse:
    return WatcherChangeEventsResponse(change_events=list_change_events(event_domain=event_domain))
