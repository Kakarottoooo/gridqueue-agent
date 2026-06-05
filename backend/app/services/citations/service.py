from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db import connect, init_database
from app.services.utils import new_id, utcnow


REFERENCE_SOURCES = (
    {
        "source_id": "src_ercot_gis_product",
        "source_name": "ERCOT GIS Report",
        "source_url": "https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er",
        "source_type": "public_source_page",
        "publication_date": None,
        "notes": "ERCOT generation interconnection status report product page.",
    },
    {
        "source_id": "src_ercot_large_load_2026_04_09",
        "source_name": "ERCOT Large Load Update, April 9 2026",
        "source_url": "https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf",
        "source_type": "public_context_pdf",
        "publication_date": "2026-04-09",
        "notes": "Large-load context only; not treated as generation queue records.",
    },
    {
        "source_id": "src_lbnl_queued_up",
        "source_name": "LBNL Queued Up",
        "source_url": "https://emp.lbl.gov/queues",
        "source_type": "public_dataset_page",
        "publication_date": None,
        "notes": "National queue context and benchmarking source.",
    },
    {
        "source_id": "src_gridstatus_docs",
        "source_name": "gridstatus interconnection queue docs",
        "source_url": "https://opensource.gridstatus.io/en/latest/interconnection_queues.html",
        "source_type": "documentation",
        "publication_date": None,
        "notes": "Optional library documentation for future ingestion adapters.",
    },
)


def ensure_reference_sources(db_path: str | Path | None = None) -> None:
    init_database(db_path)
    with connect(db_path) as con:
        for source in REFERENCE_SOURCES:
            con.execute(
                """
                INSERT OR REPLACE INTO sources
                (source_id, source_name, source_url, source_type, retrieved_at, publication_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source["source_id"],
                    source["source_name"],
                    source["source_url"],
                    source["source_type"],
                    utcnow(),
                    source["publication_date"],
                    source["notes"],
                ],
            )


def insert_record_citation(
    con: Any,
    *,
    source_id: str,
    snapshot_id: str,
    record_id: str,
    citation_label: str,
    citation_text: str,
    source_url: str,
) -> str:
    citation_id = new_id("cit")
    con.execute(
        """
        INSERT INTO citations
        (citation_id, source_id, snapshot_id, record_id, citation_label, citation_text, source_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [citation_id, source_id, snapshot_id, record_id, citation_label, citation_text, source_url, utcnow()],
    )
    return citation_id


def get_citations_for_records(record_ids: list[str], db_path: str | Path | None = None) -> list[dict[str, Any]]:
    if not record_ids:
        return []
    placeholders = ", ".join(["?"] * len(record_ids))
    with connect(db_path) as con:
        rows = con.execute(
            f"""
            SELECT citation_id, source_id, snapshot_id, record_id, citation_label, citation_text, source_url
            FROM citations
            WHERE record_id IN ({placeholders})
            ORDER BY citation_label
            """,
            record_ids,
        ).fetchall()
    return [
        {
            "citation_id": row[0],
            "source_id": row[1],
            "snapshot_id": row[2],
            "record_id": row[3],
            "citation_label": row[4],
            "citation_text": row[5],
            "source_url": row[6],
        }
        for row in rows
    ]

