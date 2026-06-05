from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_procurement_lead_time_api(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GRIDQUEUE_DB_PATH", str(tmp_path / "procurement_api.duckdb"))
    client = TestClient(app)

    seed = client.post("/procurement/lead-times/seed")
    assert seed.status_code == 200
    assert seed.json()["lead_time_count"] == 1

    response = client.get("/procurement/lead-times")
    assert response.status_code == 200
    rows = response.json()["lead_times"]
    assert rows[0]["equipment_class"] == "Large Power Transformer"
    assert rows[0]["source_url"]
    assert rows[0]["lead_time_low_months"] < rows[0]["lead_time_high_months"]
