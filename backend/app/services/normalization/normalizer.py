from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.services.utils import compact_whitespace, new_id


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "queue_id": ("queue id", "queue no", "queue number", "project code", "interconnection request id", "ir number"),
    "project_name": ("project name", "project", "generation resource", "resource name", "facility name"),
    "interconnecting_entity": ("interconnecting entity", "developer", "company", "applicant", "owner"),
    "county": ("county", "county name"),
    "state": ("state", "st"),
    "point_of_interconnection": ("point of interconnection", "poi", "substation", "interconnection point"),
    "transmission_owner": ("transmission owner", "tsp", "utility", "transmission service provider"),
    "fuel_type": ("fuel type", "technology", "resource type", "fuel", "generation type"),
    "capacity_mw": ("capacity mw", "capacity (mw)", "mw", "nameplate mw", "summer mw"),
    "status": ("status", "project status", "queue status"),
    "request_date": ("request date", "application date", "queue date"),
    "target_cod": ("target cod", "planned cod", "commercial operation date", "projected cod", "in service date"),
    "actual_cod": ("actual cod", "actual commercial operation date", "online date"),
    "withdrawn_date": ("withdrawn date", "withdrawal date"),
    "interconnection_agreement_date": ("interconnection agreement date", "ia date", "gia date"),
    "last_updated_date": ("last updated", "updated", "last updated date", "update date"),
}

BUSINESS_SUFFIXES = (
    "llc",
    "l l c",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "lp",
    "llp",
    "holdings",
    "energy",
    "renewables",
)

FUEL_KEYWORDS = (
    ("Hybrid", ("hybrid", "solar plus storage", "solar + storage", "pv+bess", "pv + bess")),
    ("Battery", ("battery", "bess", "storage", "ess")),
    ("Solar", ("solar", "photovoltaic", "pv")),
    ("Wind", ("wind",)),
    ("Gas", ("gas", "ccgt", "ct", "combined cycle", "combustion turbine")),
)

STATUS_KEYWORDS = (
    ("Withdrawn", ("withdrawn", "withdraw", "cancelled", "canceled", "terminated")),
    ("Completed", ("completed", "complete", "operational", "in service", "online", "energized")),
    ("Suspended", ("suspended", "on hold", "inactive")),
    ("Active", ("active", "studying", "in progress", "pending", "planned", "under review")),
)


def _clean_key(value: str) -> str:
    return compact_whitespace(re.sub(r"[^a-z0-9]+", " ", value.lower()))


def get_value(payload: dict[str, Any], canonical: str) -> Any:
    lookup = {_clean_key(key): key for key in payload.keys()}
    for alias in COLUMN_ALIASES[canonical]:
        source_key = lookup.get(_clean_key(alias))
        if source_key is not None:
            return payload.get(source_key)
    return None


def normalize_project_name(value: Any) -> str | None:
    if value is None or _is_missing(value):
        return None
    text = str(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    parts = [part for part in compact_whitespace(text).split(" ") if part not in BUSINESS_SUFFIXES]
    return " ".join(parts) or None


def normalize_company(value: Any) -> str | None:
    return normalize_project_name(value)


def normalize_county(value: Any) -> str | None:
    if value is None or _is_missing(value):
        return None
    text = str(value).replace("County", "").replace("county", "")
    text = compact_whitespace(re.sub(r"[^A-Za-z\s-]", " ", text))
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.split())


def normalize_state(value: Any) -> str | None:
    if value is None or _is_missing(value):
        return None
    text = str(value).strip().upper()
    if text in {"TEXAS", "TX"}:
        return "TX"
    if len(text) == 2:
        return text
    return text[:2] if text else None


def normalize_fuel_type(value: Any) -> str:
    if value is None or _is_missing(value):
        return "Unknown"
    text = str(value).lower()
    for normalized, keywords in FUEL_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return normalized
    if compact_whitespace(text):
        return "Other"
    return "Unknown"


def normalize_status(value: Any) -> str:
    if value is None or _is_missing(value):
        return "Unknown"
    text = str(value).lower()
    for normalized, keywords in STATUS_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return normalized
    return "Unknown"


def normalize_capacity_mw(value: Any) -> float | None:
    if value is None or _is_missing(value):
        return None
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        return float(value)
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def normalize_date(value: Any) -> date | None:
    if value is None or _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def normalize_text(value: Any) -> str | None:
    if value is None or _is_missing(value):
        return None
    text = compact_whitespace(str(value))
    return text or None


def normalize_record(payload: dict[str, Any], raw_record_id: str, snapshot_id: str, market: str) -> dict[str, Any]:
    project_name = normalize_text(get_value(payload, "project_name"))
    fuel_type = normalize_text(get_value(payload, "fuel_type"))
    status = normalize_text(get_value(payload, "status"))
    capacity_mw = normalize_capacity_mw(get_value(payload, "capacity_mw"))
    normalized_name = normalize_project_name(project_name)
    normalized_fuel = normalize_fuel_type(fuel_type)
    normalized_status = normalize_status(status)
    county = normalize_county(get_value(payload, "county"))
    state = normalize_state(get_value(payload, "state"))

    flags: list[str] = []
    if not get_value(payload, "queue_id"):
        flags.append("missing_queue_id")
    if not project_name:
        flags.append("missing_project_name")
    if normalized_fuel in {"Unknown", "Other"}:
        flags.append(f"unclear_fuel_type:{fuel_type or 'missing'}")
    if normalized_status == "Unknown":
        flags.append(f"unclear_status:{status or 'missing'}")
    if capacity_mw is None or capacity_mw <= 0:
        flags.append("missing_or_nonpositive_capacity_mw")
    if county is None:
        flags.append("missing_county")

    return {
        "record_id": new_id("rec"),
        "snapshot_id": snapshot_id,
        "market": market,
        "queue_id": normalize_text(get_value(payload, "queue_id")),
        "project_name": project_name,
        "normalized_project_name": normalized_name,
        "interconnecting_entity": normalize_text(get_value(payload, "interconnecting_entity")),
        "county": county,
        "state": state,
        "point_of_interconnection": normalize_text(get_value(payload, "point_of_interconnection")),
        "transmission_owner": normalize_text(get_value(payload, "transmission_owner")),
        "fuel_type": fuel_type,
        "normalized_fuel_type": normalized_fuel,
        "capacity_mw": capacity_mw,
        "status": status,
        "normalized_status": normalized_status,
        "request_date": normalize_date(get_value(payload, "request_date")),
        "target_cod": normalize_date(get_value(payload, "target_cod")),
        "actual_cod": normalize_date(get_value(payload, "actual_cod")),
        "withdrawn_date": normalize_date(get_value(payload, "withdrawn_date")),
        "interconnection_agreement_date": normalize_date(get_value(payload, "interconnection_agreement_date")),
        "last_updated_date": normalize_date(get_value(payload, "last_updated_date")),
        "raw_record_id": raw_record_id,
        "data_quality_flags_json": flags,
    }


def _is_missing(value: Any) -> bool:
    if isinstance(value, float) and math.isnan(value):
        return True
    if str(value).strip().lower() in {"", "nan", "none", "null", "nat"}:
        return True
    return False

