# Decisions

## Repository root

The requested structure named `gridqueue-agent/`, but the provided workspace is already the project checkout at
the supplied root directory. The implementation uses that checkout as the repo root so `make install`, `make test`,
and local Git commands work without an extra nested folder.

## Backend

FastAPI is used for typed local APIs and built-in OpenAPI docs. DuckDB is used as the local analytical database
because it is easy to run in a demo checkout and supports SQL over analytical tables without requiring a server.

## Data processing

Pandas is used for CSV/XLSX ingestion because it is widely available, familiar to reviewers, and sufficient for
small-to-medium public queue files. The domain logic is kept outside pandas so matching, diffing, metrics, and
brief generation remain testable service code.

## Live ingestion

The MVP supports fixture ingestion and manual ERCOT/LBNL file ingestion. Fully automatic public download is
deliberately conservative because public data-product pages can change, require dynamic navigation, or publish
files with changing names. Manual fallback is documented and testable.

## Entity resolution

The matcher is deterministic and weighted rather than embedding-based. This keeps the matching explanation visible
in `project_entity_links.match_features_json` and makes eval failures easy to diagnose.

## LLM usage

Brief generation is deterministic. `OPENAI_API_KEY` is optional and unused in the MVP. If LLM polishing is added,
it must be constrained to rewriting deterministic sections and must not add facts, numbers, or unsupported claims.

## Frontend

The frontend uses Next.js and TypeScript with a compact operations-oriented interface. The app starts with the real
workflow, not a marketing landing page: ingest fixtures, generate a brief, inspect diff, metrics, matching evidence,
citations, and evals.

## Data safety

`data/raw` and `data/processed` are gitignored. Synthetic fixtures, docs, source code, tests, and eval code are
committed; raw downloaded public files and DuckDB outputs are not.

Real validation keeps the same policy. Raw ERCOT/LBNL XLSX files are ignored, while small source manifests, hashes,
row counts, markdown reports, audit CSVs, and real eval definitions are committed. A real-data run must not fall back
to fixtures and call them real.

## Flexibility Strategy Layer

The flexibility layer is implemented as a Phase 2 extension rather than a separate project because it depends on the
same public-data baseline, citation system, DuckDB schema, FastAPI API, deterministic eval runner, and Next.js UI.

Deterministic modeling is preferred over LLM inference. Rule status, eligibility criteria, compute-cost formulas, and
benefit abstentions are structured so tests and evals can catch overclaims.

Proposed, pending, directed, context-only, or needs-review records produce contingent or unsupported outputs. They do
not produce final eligibility or quantified timeline benefits unless the seeded rule has final/approved status and a
cited `quantified_benefit_json`.

No runtime scheduling is implemented. GridQueue evaluates whether a curtailable-load commitment is worth considering;
it does not execute curtailment, schedule GPU jobs, or operate a controller.

## Monthly Watcher

The Monthly Watcher is implemented as a unified adapter layer over existing `diff_events`, regulatory source snapshots,
and flexibility rules. It does not replace the core queue diff engine. This keeps the original entity-resolution and
diff semantics intact while allowing ranked operational digests.

Source monitoring is curated rather than crawler-based. Broad scraping would create unsupported facts and noisy alerts.
The Watcher therefore stores explicit `watch_sources`, content hashes, parse status, and manual-review events.

Ambiguous queue matches are visible but not hard alerts. Parse failures are listed as manual review and are not
summarized as if parsed.

## Post-NTP Lead-Time Scaffold

The Post-NTP Lead-Time layer is a scaffold because public lead-time data is weak, non-uniform, and usually not
project-specific. V1 stores cited ranges with recency and confidence metadata for one equipment class rather than
creating a procurement product.

No firm quotes, prices, OEM ranking, RFQ workflow, or guaranteed delivery timeline are implemented.

## Time-to-Power Brief

Time-to-Power is an integration layer, not a new standalone product. It depends on GridQueue metric rollups,
Flexibility Strategy statuses, and Post-NTP lead-time rows, so duplicating those systems would create drift and weaker
provenance.

Procurement data is treated as weaker than queue data because public lead-time ranges are non-uniform, often stale,
and not project-specific. The critical path therefore preserves source rows, flags stale/conflicting data, and avoids
quotes, prices, or vendor recommendations.

Ranges are required because neither queue duration proxies nor equipment lead times support precise promises. The
engine stores low/high days and all constants, including `days_per_month = 30.4375`, in assumptions.

Proposed, pending, directed, context-only, and technical-evidence flexibility records remain contingent or unsupported.
They can shape planning context but do not become final quantified timeline reductions.

The default procurement strategy is `post_ntp_serial` because it is the conservative planning assumption. At-risk
overlap is optional and heavily caveated because early procurement can strand spend if interconnection outcomes change.

## Real Data Validation

The real validation sprint is a credibility layer over the existing system, not a new product phase. ERCOT GIS real
ingestion reuses the existing `snapshots`, `raw_project_records`, `normalized_project_records`, entity-resolution,
diff, and Watcher adapter tables. LBNL uses a dedicated project-level table because forcing the national workbook into
the ERCOT schema would lose workbook-specific fields.

Independent checks intentionally read raw XLSX files directly with pandas/openpyxl and compare simple counts/totals to
app tables and reports. They avoid circular validation by not importing the main normalization, entity-resolution, or
diff services.
