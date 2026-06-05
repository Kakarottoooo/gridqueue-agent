# Monthly Regulatory + Queue Change Watcher

The Watcher turns GridQueue's existing monthly queue diff and flexibility-rule monitoring into an operational
"what changed?" digest.

It consumes:

- existing `diff_events`
- curated regulatory `watch_sources`
- source content hashes in `source_snapshots`
- seeded flexibility-rule records

It outputs:

- unified `change_events`
- deterministic materiality ranking
- `digests/latest.md` and period markdown files
- manual-review flags for parse failures or status language that should not be auto-applied

## What It Does

- Adapts queue diff events into a unified event layer.
- Keeps ambiguous entity-resolution results visible but out of hard-alert sections.
- Snapshots curated regulatory sources by normalized content hash.
- Emits source-change, parse-failure, and needs-review events without fabricating legal conclusions.
- Generates a citation-grounded monthly digest with source URLs, event IDs, scores, confidence, and caveats.

## What It Does Not Do

- It does not crawl the web broadly.
- It does not treat parse-failed content as parsed.
- It does not silently update rule status when a page changes.
- It does not replace legal review, formal interconnection studies, power-flow studies, or project diligence.

## Curated Source Registry

Seed sources with:

```powershell
python scripts/seed_watch_sources.py
```

Curated sources are intentionally small:

- FERC RM26-4 docket page
- FERC April 16, 2026 large-load docket update
- SPP HILL / CHILL page
- FERC SPP HILL acceptance context
- internal `iso_flexibility_rules` rows
- deterministic manual fixture sources

## Running Locally

```powershell
python scripts/ingest_fixture.py
python scripts/seed_flexibility_rules.py
python scripts/seed_watch_sources.py
python scripts/run_monthly_watcher.py --mode fixture --period 2026-05
```

The CLI writes:

- `digests/latest.md`
- `digests/2026-05.md`

## API

- `GET /watcher/sources`
- `POST /watcher/sources/seed`
- `POST /watcher/run`
- `POST /watcher/queue-adapter`
- `POST /watcher/regulatory-snapshot`
- `POST /watcher/digest`
- `GET /watcher/digests`
- `GET /watcher/digests/latest`
- `GET /watcher/change-events`

## Materiality

Materiality is deterministic. Base weights are documented in `backend/app/services/watcher/materiality.py` and include
higher scores for withdrawals, rule-status changes, rule-source changes, parse failures, and large capacity movements.

Ambiguous matches are visible but receive `is_hard_alert=false`.

## Required Caveat

This digest is a public-data monitoring artifact. It does not replace formal interconnection studies, legal review,
regulatory counsel, power-flow studies, procurement quotes, or project-specific diligence.
