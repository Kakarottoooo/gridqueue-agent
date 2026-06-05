from __future__ import annotations

from pathlib import Path

from app.db import reset_database
from app.services.time_to_power import generate_time_to_power_brief, seed_time_to_power_fixtures


def test_time_to_power_fixture_demo_runs_end_to_end(tmp_path) -> None:
    db_path = tmp_path / "demo.duckdb"
    output_dir = tmp_path / "demo_outputs"
    reset_database(db_path)

    seed = seed_time_to_power_fixtures(reset_core=True, db_path=db_path)
    brief = generate_time_to_power_brief(output_dir=output_dir, db_path=db_path)

    assert seed["status"] == "seeded"
    assert brief["estimate"]["baseline"]["metric_id"]
    assert brief["estimate"]["procurement_critical_path"]["lead_time_rows"]
    assert brief["estimate"]["flexibility_adjusted"]["benefit_status"] in {"contingent", "quantified", "qualitative_only", "unsupported"}
    assert Path(brief["markdown_path"]).read_text(encoding="utf-8") == brief["markdown"]
