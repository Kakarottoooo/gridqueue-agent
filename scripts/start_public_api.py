from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_script(*args: str) -> None:
    subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        check=True,
    )


def seed_public_demo() -> None:
    """Prepare deterministic demo data for a public, stateless deployment."""
    _run_script("scripts/ingest_fixture.py")
    _run_script("scripts/seed_flexibility_rules.py")
    _run_script("scripts/seed_watch_sources.py")
    _run_script("scripts/run_monthly_watcher.py", "--mode", "fixture", "--period", "2026-05")
    _run_script("scripts/seed_lead_time_kb.py")
    _run_script("scripts/seed_time_to_power_fixtures.py")
    _run_script("scripts/run_time_to_power_demo.py")


def main() -> None:
    if os.getenv("GRIDQUEUE_PUBLIC_DEMO_SEED", "true").lower() in {"1", "true", "yes"}:
        seed_public_demo()

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", app_dir=str(PROJECT_ROOT / "backend"), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
