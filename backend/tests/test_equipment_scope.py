from __future__ import annotations

from app.services.time_to_power.equipment_scope import generate_equipment_scope


def test_equipment_scope_generates_large_load_scope() -> None:
    scope = generate_equipment_scope(project_type="AI data center load", peak_mw=300, interconnection_voltage_kv=345)
    classes = {item["equipment_class"] for item in scope["equipment_scope"]}

    assert scope["equipment_scope_mode"] == "generated_planning_model"
    assert "Large Power Transformer" in classes
    assert "HV Switchgear / GIS" in classes
    assert all(item["explanation"] for item in scope["equipment_scope"])
    assert "planning-level" in scope["caveats"][0]


def test_equipment_scope_preserves_manual_override() -> None:
    manual = [{"equipment_class": "Large Power Transformer", "notes": "User selected"}]
    scope = generate_equipment_scope(
        project_type="unknown",
        peak_mw=1,
        interconnection_voltage_kv=1,
        manual_equipment_scope_json=manual,
    )

    assert scope["equipment_scope_mode"] == "manual_user_selected"
    assert scope["equipment_scope"][0]["equipment_class"] == "Large Power Transformer"
    assert scope["equipment_scope"][0]["source"] == "manual_user_selected"


def test_equipment_scope_abstains_with_insufficient_inputs() -> None:
    scope = generate_equipment_scope(project_type="unknown", peak_mw=0, interconnection_voltage_kv=None)

    assert scope["equipment_scope_mode"] == "insufficient_data"
    assert scope["equipment_scope"] == []
    assert "abstains" in scope["caveats"][1]
