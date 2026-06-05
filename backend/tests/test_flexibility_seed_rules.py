from __future__ import annotations

from app.db import connect, reset_database
from app.services.flexibility import list_flexibility_rules, seed_flexibility_rules


def test_flexibility_seed_rules_are_idempotent_and_cited(tmp_path) -> None:
    db_path = tmp_path / "flex_seed.duckdb"
    reset_database(db_path)

    first = seed_flexibility_rules(db_path)
    second = seed_flexibility_rules(db_path)
    rules = list_flexibility_rules(db_path=db_path)

    assert first["rule_count"] == second["rule_count"] == 6
    assert {rule["jurisdiction"] for rule in rules} >= {"FERC", "SPP", "PJM", "ERCOT", "EVIDENCE", "DEMO"}
    assert all(rule["source_url"] for rule in rules)
    assert all(rule["citations"] and rule["citations"][0]["source_url"] for rule in rules)

    with connect(db_path) as con:
        source_rows = con.execute("SELECT COUNT(*) FROM flexibility_rule_sources").fetchone()[0]

    assert source_rows == 6


def test_seeded_rule_statuses_are_conservative(tmp_path) -> None:
    db_path = tmp_path / "flex_status.duckdb"
    reset_database(db_path)
    seed_flexibility_rules(db_path)

    rules = {rule["rule_id"]: rule for rule in list_flexibility_rules(db_path=db_path)}

    assert rules["rule_ferc_rm26_4_anopr"]["status"] in {"pending", "proposed"}
    assert rules["rule_pjm_colocated_load_reform"]["status"] == "directed"
    assert rules["rule_ercot_large_load_context"]["status"] == "context_only"
    assert rules["rule_emerald_epri_dcflex_evidence"]["status"] == "technical_evidence"
    assert rules["rule_gridqueue_demo_quantified_final"]["source_url"].startswith("synthetic://")
