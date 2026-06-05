from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_origins
from app.routers.api import router
from app.routers.flexibility import router as flexibility_router
from app.routers.procurement import router as procurement_router
from app.routers.watcher import router as watcher_router


app = FastAPI(
    title="GridQueue Agent API",
    description="Public-data interconnection queue monitoring, entity resolution, metrics, and risk briefs.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(flexibility_router)
app.include_router(watcher_router)
app.include_router(procurement_router)
