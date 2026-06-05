from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def project_root() -> Path:
    return ROOT_DIR


def database_path() -> Path:
    configured = os.getenv("GRIDQUEUE_DB_PATH", "data/processed/gridqueue.duckdb")
    path = Path(configured)
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fixtures_dir() -> Path:
    return ROOT_DIR / "data" / "fixtures"


def raw_dir() -> Path:
    path = ROOT_DIR / "data" / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path

