from __future__ import annotations

from app.db import reset_database
from app.services.time_to_power.fixtures import seed_time_to_power_fixtures
from app.services.time_to_power.flex_adjusted import calculate_flex_adjusted_interconnection
from app.services.time_to_power.interconnection_baseline import get_interconnection_baseline


def test_flex_adjusted_keeps_proposed_rule_contingent(tmp_path) -> None:
    db_path = tmp_path / "flex_adjusted.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)
    baseline = get_interconnection_baseline(market="ERCOT", county="Reeves", project_type="AI data center load", min_sample_n=2, db_path=db_path)

    flex = calculate_flex_adjusted_interconnection(
        market="ERCOT",
        jurisdiction="FERC",
        county="Reeves",
        peak_mw=300,
        average_load_factor=0.85,
        commitment_depth_pct=20,
        event_duration_hours=3,
        events_per_year=20,
        baseline=baseline,
        min_sample_n=2,
        db_path=db_path,
    )

    assert flex["rule_status"] == "pending"
    assert flex["benefit_status"] == "contingent"
    assert flex["interconnection_with_flex_low_days"] is None
    assert "contingent" in " ".join(flex["caveats"])


def test_flex_adjusted_does_not_treat_technical_evidence_as_regulation(tmp_path) -> None:
    db_path = tmp_path / "flex_evidence.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)
    baseline = get_interconnection_baseline(market="ERCOT", county="Reeves", project_type="AI data center load", min_sample_n=2, db_path=db_path)

    flex = calculate_flex_adjusted_interconnection(
        market="ERCOT",
        jurisdiction="EVIDENCE",
        county="Reeves",
        peak_mw=300,
        average_load_factor=0.85,
        commitment_depth_pct=25,
        event_duration_hours=3,
        events_per_year=20,
        baseline=baseline,
        min_sample_n=2,
        db_path=db_path,
    )

    assert flex["rule_status"] == "technical_evidence"
    assert flex["benefit_status"] == "unsupported"
    assert any("Technical evidence" in caveat for caveat in flex["caveats"])
