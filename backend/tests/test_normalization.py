from __future__ import annotations

from app.services.normalization import normalize_capacity_mw, normalize_county, normalize_fuel_type, normalize_project_name, normalize_status


def test_project_name_normalization_removes_punctuation_and_business_suffixes() -> None:
    assert normalize_project_name("Pecos Battery Storage, Inc.") == "pecos battery storage"
    assert normalize_project_name("Lone Star Solar LLC") == "lone star solar"


def test_core_normalizers_make_unknowns_explicit() -> None:
    assert normalize_county("Reeves County") == "Reeves"
    assert normalize_fuel_type("Solar + Storage") == "Hybrid"
    assert normalize_fuel_type("BESS") == "Battery"
    assert normalize_status("In Service") == "Completed"
    assert normalize_status("mystery") == "Unknown"
    assert normalize_capacity_mw("100.5 MW") == 100.5

