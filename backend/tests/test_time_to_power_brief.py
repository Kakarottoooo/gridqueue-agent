from __future__ import annotations

from pathlib import Path

from app.db import reset_database
from app.services.time_to_power import generate_time_to_power_brief, seed_time_to_power_fixtures
from app.services.time_to_power.brief import TIME_TO_POWER_CAVEAT


def test_time_to_power_brief_includes_sections_caveat_and_provenance(tmp_path) -> None:
    db_path = tmp_path / "brief.duckdb"
    out_dir = tmp_path / "briefs"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)

    brief = generate_time_to_power_brief(output_dir=out_dir, db_path=db_path)
    markdown = brief["markdown"]

    for section in [
        "Executive summary",
        "Project scenario",
        "Interconnection baseline",
        "Flexibility-adjusted scenario",
        "Procurement critical path",
        "Energization timeline",
        "Scenario comparison table",
        "Binding constraints",
        "Assumptions",
        "Citations",
        "Reproducibility trace",
        "Caveats and abstentions",
    ]:
        assert f"## {section}" in markdown
    assert TIME_TO_POWER_CAVEAT in markdown
    assert "metric_id:" in markdown
    assert "sample_n:" in markdown
    assert "source_snapshot_id:" in markdown
    assert brief["citations"]
    assert Path(brief["markdown_path"]).exists()
    assert "guaranteed energization" not in markdown.lower()
