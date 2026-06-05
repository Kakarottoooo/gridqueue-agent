from __future__ import annotations

from app.db import reset_database
from app.services.time_to_power.fixtures import seed_time_to_power_fixtures
from app.services.time_to_power.interconnection_baseline import get_interconnection_baseline


def test_baseline_adapter_returns_metric_trace(tmp_path) -> None:
    db_path = tmp_path / "baseline.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)

    baseline = get_interconnection_baseline(
        market="ERCOT",
        county="Reeves",
        project_type="AI data center load",
        peak_mw=300,
        target_online_year=2029,
        min_sample_n=2,
        db_path=db_path,
    )

    assert baseline["status"] == "complete"
    assert baseline["metric_id"].startswith("met_")
    assert baseline["sample_n"] >= 2
    assert baseline["fallback_level"]
    assert baseline["confidence"] in {"Low", "Medium", "High"}
    assert baseline["source_snapshot_id"]
    assert baseline["citations"][0]["source_url"]


def test_baseline_adapter_abstains_when_sample_insufficient(tmp_path) -> None:
    db_path = tmp_path / "baseline_insufficient.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)

    baseline = get_interconnection_baseline(
        market="ERCOT",
        county="Reeves",
        project_type="AI data center load",
        min_sample_n=100,
        db_path=db_path,
    )

    assert baseline["status"] == "insufficient_interconnection_baseline"
    assert baseline["baseline_low_days"] is None
    assert baseline["confidence"] == "Insufficient"
