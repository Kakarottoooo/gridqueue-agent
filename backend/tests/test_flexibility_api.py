from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_flexibility_api_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GRIDQUEUE_DB_PATH", str(tmp_path / "flex_api.duckdb"))
    client = TestClient(app)

    assert client.post("/ingest/fixtures").status_code == 200
    seed = client.post("/flexibility/seed")
    assert seed.status_code == 200
    assert seed.json()["rule_count"] >= 5

    rules = client.get("/flexibility/rules")
    assert rules.status_code == 200
    assert rules.json()["rules"]

    payload = {
        "market": "ERCOT",
        "jurisdiction": "FERC",
        "county": "Reeves",
        "peak_mw": 100,
        "average_load_factor": 0.85,
        "commitment_depth_pct": 25,
        "event_duration_hours": 3,
        "events_per_year": 20,
        "dispatchable_or_curtailable": True,
        "metering_or_control_capability": True,
        "min_sample_n": 2,
    }

    compute = client.post("/flexibility/compute-cost", json=payload)
    assert compute.status_code == 200
    assert compute.json()["compute_cost"]["assumptions_json"]["gpu_power_kw"] == 0.7

    eligibility = client.post("/flexibility/eligibility", json=payload)
    assert eligibility.status_code == 200
    assert eligibility.json()["eligibility_results"][0]["eligibility_status"] == "contingent"

    tradeoff = client.post("/flexibility/tradeoff", json=payload)
    assert tradeoff.status_code == 200
    assert tradeoff.json()["tradeoff_points"]

    brief = client.post("/flexibility/brief", json=payload)
    assert brief.status_code == 200
    assert brief.json()["brief"]["title"] == "Flexibility Strategy Brief"
