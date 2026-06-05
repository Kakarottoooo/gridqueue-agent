from __future__ import annotations

from app.db import reset_database
from app.services.time_to_power import generate_time_to_power_estimate, seed_time_to_power_fixtures


def test_time_to_power_estimate_serial_and_overlap_math(tmp_path) -> None:
    db_path = tmp_path / "estimate.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)

    estimate = generate_time_to_power_estimate(db_path=db_path)
    baseline = estimate["baseline"]
    procurement = estimate["procurement_critical_path"]
    commissioning = estimate["commissioning_assumption"]

    assert estimate["no_flex_serial_low_days"] == round(
        baseline["baseline_low_days"]
        + procurement["procurement_low_days"]
        + commissioning["default_commissioning_low_days"]
        + commissioning["energization_buffer_low_days"],
        2,
    )
    assert estimate["no_flex_overlap_high_days"] == round(
        max(baseline["baseline_high_days"], procurement["procurement_high_days"])
        + commissioning["default_commissioning_high_days"]
        + commissioning["energization_buffer_high_days"],
        2,
    )
    assert estimate["selected_case"] == "no_flex_serial"
    assert estimate["flex_serial_low_days"] is None
    assert estimate["flexibility_adjusted"]["benefit_status"] == "contingent"


def test_time_to_power_estimate_overlap_strategy_caveat_and_flex_no_procurement_change(tmp_path) -> None:
    db_path = tmp_path / "estimate_overlap.duckdb"
    reset_database(db_path)
    seed_time_to_power_fixtures(reset_core=True, db_path=db_path)

    estimate = generate_time_to_power_estimate(
        jurisdiction="DEMO",
        procurement_strategy="at_risk_overlap",
        commitment_depth_pct=20,
        db_path=db_path,
    )

    assert estimate["selected_case"] == "flex_overlap"
    assert estimate["procurement_critical_path"]["procurement_low_days"] == estimate["procurement_critical_path"]["procurement_low_days"]
    assert estimate["flexibility_adjusted"]["benefit_status"] == "quantified"
    assert estimate["flex_overlap_low_days"] is not None
    assert any("At-risk overlap" in caveat for caveat in estimate["caveats"])
