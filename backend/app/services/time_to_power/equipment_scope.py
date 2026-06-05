from __future__ import annotations

from typing import Any


SCOPE_CAVEAT = (
    "Equipment scope is a planning-level model only. It is not a stamped engineering design, EPC scope, OEM RFQ, "
    "or guarantee that these are the exact project facilities."
)


def generate_equipment_scope(
    *,
    project_type: str,
    peak_mw: float,
    interconnection_voltage_kv: float | None,
    manual_equipment_scope_json: list[dict[str, Any]] | dict[str, Any] | None = None,
    equipment_scope_mode: str = "generated_planning_model",
) -> dict[str, Any]:
    if manual_equipment_scope_json:
        items = _manual_items(manual_equipment_scope_json)
        return {
            "equipment_scope_mode": "manual_user_selected",
            "equipment_scope": items,
            "confidence": "user_supplied",
            "assumptions": {"source": "manual_equipment_scope_json", "item_count": len(items)},
            "caveats": [SCOPE_CAVEAT, "Manual equipment items are preserved as supplied and are not validated as engineering design."],
        }

    if peak_mw <= 0 or interconnection_voltage_kv is None or interconnection_voltage_kv <= 0:
        return {
            "equipment_scope_mode": "insufficient_data",
            "equipment_scope": [],
            "confidence": "insufficient",
            "assumptions": {
                "required_inputs": ["project_type", "peak_mw", "interconnection_voltage_kv"],
                "received": {
                    "project_type": project_type,
                    "peak_mw": peak_mw,
                    "interconnection_voltage_kv": interconnection_voltage_kv,
                },
            },
            "caveats": [SCOPE_CAVEAT, "GridQueue abstains from equipment scoping because required planning inputs are missing."],
        }

    normalized = project_type.strip().lower()
    if normalized in {"ai data center load", "data center load", "generic large load", "large load"}:
        items = _large_load_scope(peak_mw, interconnection_voltage_kv)
    elif normalized in {"battery", "battery storage", "storage"}:
        items = _battery_scope(peak_mw, interconnection_voltage_kv)
    elif normalized in {"solar + storage", "solar storage", "hybrid", "solar and storage"}:
        items = _solar_storage_scope(peak_mw, interconnection_voltage_kv)
    else:
        return {
            "equipment_scope_mode": "insufficient_data",
            "equipment_scope": [],
            "confidence": "insufficient",
            "assumptions": {"project_type": project_type},
            "caveats": [SCOPE_CAVEAT, f"No deterministic planning scope rule exists for project_type={project_type}."],
        }

    return {
        "equipment_scope_mode": "fixture_demo" if equipment_scope_mode == "fixture_demo" else "generated_planning_model",
        "equipment_scope": items,
        "confidence": "low",
        "assumptions": {
            "project_type": project_type,
            "peak_mw": peak_mw,
            "interconnection_voltage_kv": interconnection_voltage_kv,
            "model_version": "time_to_power_scope_v1",
        },
        "caveats": [SCOPE_CAVEAT],
    }


def _manual_items(value: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = value.get("equipment_scope", []) if isinstance(value, dict) else value
    return [
        {
            **item,
            "scope_item_id": item.get("scope_item_id") or f"manual_{index + 1}",
            "source": "manual_user_selected",
            "explanation": item.get("explanation") or "Manual item supplied by user.",
        }
        for index, item in enumerate(raw_items)
    ]


def _large_load_scope(peak_mw: float, voltage: float) -> list[dict[str, Any]]:
    items = [
        _item("Large Power Transformer", "Bulk supply transformer is a likely long-lead item for a high-MW large-load interconnection."),
        _item("Medium-Voltage Switchgear", "Large-load campuses usually require medium-voltage distribution switching."),
        _item("Protection / Control / Metering Package", "Interconnection protection, control, and metering packages are required planning facilities."),
        _item("Interconnection Facilities", "POI and owner interconnection facilities are included as planning-level scope."),
        _item("Commissioning / Testing Package", "Commissioning and acceptance testing are modeled separately as an assumption."),
    ]
    if voltage >= 230 or peak_mw >= 100:
        items.insert(1, _item("HV Switchgear / GIS", "Transmission-voltage or large-MW interconnections commonly require high-voltage switching equipment."))
    return items


def _battery_scope(peak_mw: float, voltage: float) -> list[dict[str, Any]]:
    items = [
        _item("GSU Transformer", "Battery projects typically require a generator step-up transformer or equivalent transformation."),
        _item("Medium-Voltage Switchgear", "Collector and medium-voltage switching is included in planning-level scope."),
        _item("Protection / Control / Metering Package", "Protection, control, and metering are required for interconnection."),
        _item("Interconnection Facilities", "POI interconnection facilities are modeled as planning-level scope."),
        _item("Commissioning / Testing Package", "Commissioning and testing are modeled separately as an assumption."),
    ]
    if voltage >= 230 or peak_mw >= 100:
        items.insert(1, _item("HV Switchgear / GIS", "High-voltage interconnection can require transmission-class switchgear or GIS."))
    return items


def _solar_storage_scope(peak_mw: float, voltage: float) -> list[dict[str, Any]]:
    items = _battery_scope(peak_mw, voltage)
    items.insert(0, _item("GSU Transformer", "Solar-plus-storage projects usually require step-up transformation from collector voltage to interconnection voltage."))
    return _dedupe(items)


def _item(equipment_class: str, explanation: str) -> dict[str, Any]:
    return {
        "scope_item_id": f"scope_{equipment_class.lower().replace(' ', '_').replace('/', '').replace('-', '_')}",
        "equipment_class": equipment_class,
        "source": "deterministic_planning_model",
        "explanation": explanation,
    }


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item["equipment_class"] not in seen:
            seen.add(item["equipment_class"])
            result.append(item)
    return result
