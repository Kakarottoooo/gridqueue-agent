from __future__ import annotations

from app.services.flexibility import generate_flexibility_brief, get_compute_assumption, seed_flexibility_rules
from app.services.flexibility.brief import FLEXIBILITY_CAVEAT
from app.services.ingestion import run_fixture_pipeline


def test_flexibility_brief_contains_caveat_status_assumptions_and_citations(tmp_path) -> None:
    db_path = tmp_path / "flex_brief.duckdb"
    run_fixture_pipeline(db_path, reset=True)
    seed_flexibility_rules(db_path)
    assumption = get_compute_assumption(db_path=db_path)

    brief = generate_flexibility_brief(
        market="ERCOT",
        jurisdiction="FERC",
        county="Reeves",
        peak_mw=100,
        average_load_factor=0.85,
        commitment_depth_pct=25,
        event_duration_hours=3,
        events_per_year=20,
        job_mix_json={},
        colocated_generation=False,
        dispatchable_or_curtailable=True,
        metering_or_control_capability=True,
        assumption=assumption,
        min_sample_n=2,
        db_path=db_path,
    )

    assert FLEXIBILITY_CAVEAT in brief["caveats_and_abstentions"]
    assert brief["relevant_flexibility_rules"][0]["rule_status"] in {"pending", "proposed"}
    assert brief["assumptions"]["compute_cost_assumption"]["assumption_id"] == assumption["assumption_id"]
    assert brief["citations"] and all(citation["source_url"] for citation in brief["citations"])
    assert "will be approved" not in brief["markdown"].lower()
    assert "actual grid capacity" not in brief["markdown"].lower()
