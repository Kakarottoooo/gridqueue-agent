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
