from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.utils import stable_json, utcnow


DEFAULT_ASSUMPTION_ID = "assumption_dcflex_public_anchor_v1"


SOURCES: tuple[dict[str, Any], ...] = (
    {
        "source_id": "src_ferc_rm26_4",
        "source_name": "FERC RM26-4 large-load interconnection docket",
        "source_url": "https://www.ferc.gov/rm26-4",
        "source_type": "federal_rulemaking_docket",
        "publication_date": None,
        "notes": "FERC docket page for an ANOPR on interconnection of large loads.",
    },
    {
        "source_id": "src_ferc_large_load_update_2026_04_16",
        "source_name": "FERC April 16 2026 large-load docket update",
        "source_url": "https://www.ferc.gov/news-events/news/ferc-act-large-load-interconnection-docket-june-2026",
        "source_type": "federal_news_release",
        "publication_date": "2026-04-16",
        "notes": "FERC news release describing planned action on the RM26-4 ANOPR proceeding by June 2026.",
    },
    {
        "source_id": "src_spp_hill_integration",
        "source_name": "SPP High Impact Large Load integration page",
        "source_url": "https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/",
        "source_type": "iso_program_page",
        "publication_date": None,
        "notes": "SPP public description of HILL, HILLGA, and CHILL concepts.",
    },
    {
        "source_id": "src_ferc_spp_hill_concurrence",
        "source_name": "FERC concurrence on SPP HILL tariff revisions",
        "source_url": "https://www.ferc.gov/news-events/news/commissioner-rosners-concurrence-order-accepting-tariff-revisions-subject",
        "source_type": "federal_commissioner_statement",
        "publication_date": None,
        "notes": "Commissioner concurrence stating the order accepts SPP's HILL/HILLGA proposal subject to condition.",
    },
    {
        "source_id": "src_ferc_pjm_colocated_load_fact_sheet",
        "source_name": "FERC PJM co-located load fact sheet",
        "source_url": "https://www.ferc.gov/news-events/news/fact-sheet-ferc-directs-nations-largest-grid-operator-create-new-rules-embrace",
        "source_type": "federal_fact_sheet",
        "publication_date": "2025-12-18",
        "notes": "FERC fact sheet directing PJM to establish clearer rules for co-located loads.",
    },
    {
        "source_id": "src_ercot_large_load_2026_04_09",
        "source_name": "ERCOT Large Load Update, April 9 2026",
        "source_url": "https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf",
        "source_type": "public_context_pdf",
        "publication_date": "2026-04-09",
        "notes": "ERCOT large-load context only; not a verified curtailable-load fast-track rule.",
    },
    {
        "source_id": "src_emerald_epri_dcflex_arxiv_2507",
        "source_name": "Emerald AI / EPRI DCFlex field demonstration paper",
        "source_url": "https://arxiv.org/html/2507.00909v1",
        "source_type": "technical_evidence",
        "publication_date": None,
        "notes": "Technical evidence anchor for data-center flexibility; not a regulatory rule.",
    },
    {
        "source_id": "src_gridqueue_demo_quantified_flex_rule",
        "source_name": "GridQueue synthetic quantified flexibility rule",
        "source_url": "synthetic://gridqueue-agent/fixtures/flexibility-quantified-benefit",
        "source_type": "synthetic_fixture",
        "publication_date": None,
        "notes": "Synthetic fixture used only to test quantified recommendation math.",
    },
)


RULES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "rule_ferc_rm26_4_anopr",
        "jurisdiction": "FERC",
        "provision_name": "Large Load Interconnection ANOPR",
        "provision_type": "federal_rulemaking",
        "eligibility_criteria_json": {
            "peak_mw_threshold": 20,
            "curtailability_required": True,
            "metering_or_control_required": True,
            "market_or_jurisdiction": "FERC",
        },
        "granted_benefit_text": (
            "Potential reforms under consideration for timely, orderly, reliable, and non-discriminatory "
            "large-load interconnection; flexible/curtailable faster-study concepts are questions in an ANOPR."
        ),
        "quantified_benefit_json": {},
        "status": "pending",
        "effective_date": None,
        "expiration_date": None,
        "source_id": "src_ferc_rm26_4",
        "source_url": "https://www.ferc.gov/rm26-4",
        "notes": "Seeded as pending/proposed. Do not treat as final or quantified.",
        "citation_text": "FERC describes RM26-4 as an ANOPR seeking input on potential large-load interconnection reforms.",
    },
    {
        "rule_id": "rule_spp_hill_chill",
        "jurisdiction": "SPP",
        "provision_name": "High Impact Large Load / Conditional HILL Service",
        "provision_type": "ISO_large_load_process",
        "eligibility_criteria_json": {
            "peak_mw_threshold": 100,
            "curtailability_required": True,
            "metering_or_control_required": True,
            "market_or_jurisdiction": "SPP",
        },
        "granted_benefit_text": (
            "SPP describes HILL/HILLGA and CHILL as a coordinated large-load process with conditional access and "
            "potential curtailment during system stress."
        ),
        "quantified_benefit_json": {},
        "status": "approved",
        "effective_date": None,
        "expiration_date": None,
        "source_id": "src_spp_hill_integration",
        "source_url": "https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/",
        "notes": "Seeded as approved based on FERC/SPP public materials, but without quantified benefit values.",
        "citation_text": "SPP describes CHILL service as conditional grid access with potential curtailment during system stress.",
    },
    {
        "rule_id": "rule_pjm_colocated_load_reform",
        "jurisdiction": "PJM",
        "provision_name": "Co-located Load Transmission Service Reform",
        "provision_type": "co_located_load",
        "eligibility_criteria_json": {
            "colocation_required": True,
            "metering_or_control_required": True,
            "market_or_jurisdiction": "PJM",
        },
        "granted_benefit_text": "FERC directed PJM to establish transparent rules for service to co-located large loads.",
        "quantified_benefit_json": {},
        "status": "directed",
        "effective_date": None,
        "expiration_date": None,
        "source_id": "src_ferc_pjm_colocated_load_fact_sheet",
        "source_url": "https://www.ferc.gov/news-events/news/fact-sheet-ferc-directs-nations-largest-grid-operator-create-new-rules-embrace",
        "notes": "Seeded as directed/reform pending, not final tariff terms.",
        "citation_text": "FERC directed PJM to establish transparent rules for AI-driven data centers and other large loads co-located with generation.",
    },
    {
        "rule_id": "rule_ercot_large_load_context",
        "jurisdiction": "ERCOT",
        "provision_name": "Large Load Interconnection Context",
        "provision_type": "large_load_context",
        "eligibility_criteria_json": {"market_or_jurisdiction": "ERCOT"},
        "granted_benefit_text": "ERCOT public materials describe large-load growth and batch-process discussions, not a verified curtailable-load fast-track.",
        "quantified_benefit_json": {},
        "status": "context_only",
        "effective_date": None,
        "expiration_date": None,
        "source_id": "src_ercot_large_load_2026_04_09",
        "source_url": "https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf",
        "notes": "Context only until a specific final curtailable-load provision is verified.",
        "citation_text": "ERCOT materials describe large-load requests and movement toward a batch study framework.",
    },
    {
        "rule_id": "rule_emerald_epri_dcflex_evidence",
        "jurisdiction": "EVIDENCE",
        "provision_name": "Data center flexibility field demonstration",
        "provision_type": "compute_flexibility_evidence",
        "eligibility_criteria_json": {},
        "granted_benefit_text": "Technical evidence that a 256-GPU cluster demonstrated a 25 percent power reduction for three hours; not an ISO/RTO rule.",
        "quantified_benefit_json": {
            "field_demo_commitment_depth_pct": 25,
            "field_demo_event_duration_hours": 3,
            "cluster_gpus": 256,
        },
        "status": "technical_evidence",
        "effective_date": None,
        "expiration_date": None,
        "source_id": "src_emerald_epri_dcflex_arxiv_2507",
        "source_url": "https://arxiv.org/html/2507.00909v1",
        "notes": "Evidence anchor for compute-cost extrapolation flags, not a regulatory eligibility rule.",
        "citation_text": "The field demonstration reports a 25 percent reduction in cluster power for three hours on a 256-GPU cluster.",
    },
    {
        "rule_id": "rule_gridqueue_demo_quantified_final",
        "jurisdiction": "DEMO",
        "provision_name": "Synthetic quantified flexibility benefit",
        "provision_type": "fixture_demo_quantified_benefit",
        "eligibility_criteria_json": {
            "peak_mw_threshold": 20,
            "commitment_depth_pct_min": 10,
            "curtailability_required": True,
            "metering_or_control_required": True,
            "market_or_jurisdiction": "DEMO",
        },
        "granted_benefit_text": "Synthetic fixture only: used to validate quantified tradeoff and recommendation logic.",
        "quantified_benefit_json": {
            "demo_only": True,
            "timeline_delta_days_by_commitment_pct": [
                {"commitment_depth_pct": 0, "estimated_timeline_delta_days": 0},
                {"commitment_depth_pct": 10, "estimated_timeline_delta_days": 20},
                {"commitment_depth_pct": 20, "estimated_timeline_delta_days": 45},
                {"commitment_depth_pct": 25, "estimated_timeline_delta_days": 55},
                {"commitment_depth_pct": 30, "estimated_timeline_delta_days": 60},
            ],
        },
        "status": "final",
        "effective_date": None,
        "expiration_date": None,
        "source_id": "src_gridqueue_demo_quantified_flex_rule",
        "source_url": "synthetic://gridqueue-agent/fixtures/flexibility-quantified-benefit",
        "notes": "Synthetic quantified rule; never present as a real-world tariff or public rule.",
        "citation_text": "Synthetic fixture record for testing quantified net-benefit scoring.",
    },
)


DEFAULT_ASSUMPTION: dict[str, Any] = {
    "assumption_id": DEFAULT_ASSUMPTION_ID,
    "assumption_name": "Public DCFlex anchor scenario",
    "version": "1",
    "peak_mw": 100.0,
    "average_load_factor": 0.85,
    "deferrable_workload_fraction": 0.55,
    "latency_sensitive_fraction": 0.25,
    "migratable_fraction": 0.20,
    "gpu_power_kw": 0.7,
    "gpu_hour_value_usd": 3.0,
    "deferral_penalty_per_gpu_hour_usd": 0.25,
    "migration_penalty_per_gpu_hour_usd": 0.75,
    "dropped_work_penalty_per_gpu_hour_usd": 4.0,
    "default_event_duration_hours": 3.0,
    "default_events_per_year": 20,
    "evidence_anchor_json": {
        "source_id": "src_emerald_epri_dcflex_arxiv_2507",
        "source_url": "https://arxiv.org/html/2507.00909v1",
        "field_demo_commitment_depth_pct": 25,
        "field_demo_event_duration_hours": 3,
        "cluster_gpus": 256,
        "assumption_note": "GPU power and penalty values are scenario assumptions, not values claimed by the paper.",
    },
    "notes": "Default demo assumptions. Users should replace these with project-specific economics before real decisions.",
}


def seed_flexibility_rules(db_path: str | Path | None = None) -> dict[str, Any]:
    init_database(db_path)
    with connect(db_path) as con:
        for source in SOURCES:
            _upsert_source(con, source)
        for rule in RULES:
            con.execute("DELETE FROM flexibility_rule_sources WHERE rule_id = ?", [rule["rule_id"]])
            _upsert_rule(con, rule)
            con.execute(
                """
                INSERT INTO flexibility_rule_sources
                (rule_source_id, rule_id, source_id, citation_label, citation_text, source_url, retrieved_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    f"frs_{rule['rule_id']}",
                    rule["rule_id"],
                    rule["source_id"],
                    rule["provision_name"],
                    rule["citation_text"],
                    rule["source_url"],
                    utcnow(),
                    utcnow(),
                ],
            )
        _upsert_assumption(con, DEFAULT_ASSUMPTION)
        rule_count = con.execute("SELECT COUNT(*) FROM iso_flexibility_rules").fetchone()[0]
        assumption_count = con.execute("SELECT COUNT(*) FROM compute_cost_assumptions").fetchone()[0]
    return {"status": "seeded", "rule_count": int(rule_count), "assumption_count": int(assumption_count)}


def list_flexibility_rules(
    *,
    jurisdiction: str | None = None,
    include_evidence: bool = True,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_database(db_path)
    filters: list[str] = []
    params: list[Any] = []
    if jurisdiction:
        filters.append("jurisdiction = ?")
        params.append(jurisdiction)
    if not include_evidence:
        filters.append("status <> 'technical_evidence'")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect(db_path) as con:
        rows = con.execute(
            f"""
            SELECT rule_id, jurisdiction, provision_name, provision_type, eligibility_criteria_json,
                   granted_benefit_text, quantified_benefit_json, status, effective_date, expiration_date,
                   source_id, source_url, retrieved_at, notes, created_at, updated_at
            FROM iso_flexibility_rules
            {where}
            ORDER BY jurisdiction, provision_name
            """,
            params,
        ).fetchall()
        return [_rule_from_row(con, row) for row in rows]


def get_rule(rule_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_database(db_path)
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT rule_id, jurisdiction, provision_name, provision_type, eligibility_criteria_json,
                   granted_benefit_text, quantified_benefit_json, status, effective_date, expiration_date,
                   source_id, source_url, retrieved_at, notes, created_at, updated_at
            FROM iso_flexibility_rules
            WHERE rule_id = ?
            """,
            [rule_id],
        ).fetchone()
        return _rule_from_row(con, row) if row else None


def _rule_from_row(con: Any, row: Any) -> dict[str, Any]:
    rule_id = row[0]
    citations = con.execute(
        """
        SELECT rule_source_id, source_id, citation_label, citation_text, source_url, retrieved_at
        FROM flexibility_rule_sources
        WHERE rule_id = ?
        ORDER BY citation_label
        """,
        [rule_id],
    ).fetchall()
    return {
        "rule_id": rule_id,
        "jurisdiction": row[1],
        "provision_name": row[2],
        "provision_type": row[3],
        "eligibility_criteria_json": _json(row[4]),
        "granted_benefit_text": row[5],
        "quantified_benefit_json": _json(row[6]),
        "status": row[7],
        "effective_date": row[8].isoformat() if hasattr(row[8], "isoformat") else row[8],
        "expiration_date": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
        "source_id": row[10],
        "source_url": row[11],
        "retrieved_at": row[12].isoformat() if hasattr(row[12], "isoformat") else row[12],
        "notes": row[13],
        "created_at": row[14].isoformat() if hasattr(row[14], "isoformat") else row[14],
        "updated_at": row[15].isoformat() if hasattr(row[15], "isoformat") else row[15],
        "citations": [
            {
                "rule_source_id": citation[0],
                "source_id": citation[1],
                "citation_label": citation[2],
                "citation_text": citation[3],
                "source_url": citation[4],
                "retrieved_at": citation[5].isoformat() if hasattr(citation[5], "isoformat") else citation[5],
            }
            for citation in citations
        ],
    }


def _upsert_assumption(con: Any, assumption: dict[str, Any]) -> None:
    values = [
        assumption["assumption_name"],
        assumption["version"],
        assumption["peak_mw"],
        assumption["average_load_factor"],
        assumption["deferrable_workload_fraction"],
        assumption["latency_sensitive_fraction"],
        assumption["migratable_fraction"],
        assumption["gpu_power_kw"],
        assumption["gpu_hour_value_usd"],
        assumption["deferral_penalty_per_gpu_hour_usd"],
        assumption["migration_penalty_per_gpu_hour_usd"],
        assumption["dropped_work_penalty_per_gpu_hour_usd"],
        assumption["default_event_duration_hours"],
        assumption["default_events_per_year"],
        stable_json(assumption["evidence_anchor_json"]),
        assumption["notes"],
    ]
    exists = con.execute(
        "SELECT COUNT(*) FROM compute_cost_assumptions WHERE assumption_id = ?",
        [assumption["assumption_id"]],
    ).fetchone()[0]
    if exists:
        return
    else:
        con.execute(
            """
            INSERT INTO compute_cost_assumptions
            (assumption_id, assumption_name, version, peak_mw, average_load_factor,
             deferrable_workload_fraction, latency_sensitive_fraction, migratable_fraction,
             gpu_power_kw, gpu_hour_value_usd, deferral_penalty_per_gpu_hour_usd,
             migration_penalty_per_gpu_hour_usd, dropped_work_penalty_per_gpu_hour_usd,
             default_event_duration_hours, default_events_per_year, evidence_anchor_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [assumption["assumption_id"], *values, utcnow()],
        )


def _upsert_source(con: Any, source: dict[str, Any]) -> None:
    values = [
        source["source_name"],
        source["source_url"],
        source["source_type"],
        utcnow(),
        source["publication_date"],
        source["notes"],
    ]
    exists = con.execute("SELECT COUNT(*) FROM sources WHERE source_id = ?", [source["source_id"]]).fetchone()[0]
    if exists:
        return
    else:
        con.execute(
            """
            INSERT INTO sources
            (source_id, source_name, source_url, source_type, retrieved_at, publication_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [source["source_id"], *values],
        )


def _upsert_rule(con: Any, rule: dict[str, Any]) -> None:
    values = [
        rule["jurisdiction"],
        rule["provision_name"],
        rule["provision_type"],
        stable_json(rule["eligibility_criteria_json"]),
        rule["granted_benefit_text"],
        stable_json(rule["quantified_benefit_json"]),
        rule["status"],
        rule["effective_date"],
        rule["expiration_date"],
        rule["source_id"],
        rule["source_url"],
        utcnow(),
        rule["notes"],
        utcnow(),
    ]
    exists = con.execute(
        "SELECT COUNT(*) FROM iso_flexibility_rules WHERE rule_id = ?",
        [rule["rule_id"]],
    ).fetchone()[0]
    if exists:
        return
    else:
        con.execute(
            """
            INSERT INTO iso_flexibility_rules
            (rule_id, jurisdiction, provision_name, provision_type, eligibility_criteria_json,
             granted_benefit_text, quantified_benefit_json, status, effective_date, expiration_date,
             source_id, source_url, retrieved_at, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [rule["rule_id"], *values[:-1], utcnow(), values[-1]],
        )


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
