from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_time_to_power_api_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GRIDQUEUE_DB_PATH", str(tmp_path / "time_to_power_api.duckdb"))
    client = TestClient(app)

    assert client.get("/time-to-power/health").status_code == 200
    assert client.post("/time-to-power/fixtures/seed").status_code == 200

    payload = {
        "market": "ERCOT",
        "jurisdiction": "FERC",
        "county": "Reeves",
        "project_type": "AI data center load",
        "peak_mw": 300,
        "interconnection_voltage_kv": 345,
        "commitment_depth_pct": 20,
        "min_sample_n": 2,
    }

    scope = client.post("/time-to-power/equipment-scope", json=payload)
    assert scope.status_code == 200
    assert scope.json()["equipment_scope"]["equipment_scope"]

    baseline = client.post("/time-to-power/interconnection-baseline", json=payload)
    assert baseline.status_code == 200
    assert baseline.json()["baseline"]["sample_n"] >= 2

    critical = client.post("/time-to-power/procurement-critical-path", json=payload)
    assert critical.status_code == 200
    assert critical.json()["critical_path"]["binding_equipment_class"] == "Large Power Transformer"

    estimate = client.post("/time-to-power/estimate", json=payload)
    assert estimate.status_code == 200
    assert estimate.json()["estimate"]["selected_case"] == "no_flex_serial"

    brief = client.post("/time-to-power/brief", json=payload)
    assert brief.status_code == 200
    assert brief.json()["brief"]["title"].startswith("Time-to-Power Brief")

    latest = client.get("/time-to-power/briefs/latest")
    assert latest.status_code == 200
    assert latest.json()["brief"]["brief_id"] == brief.json()["brief"]["brief_id"]
