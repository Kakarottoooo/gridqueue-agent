# GridQueue Agent Project Brief

GridQueue Agent is a local-first public-data intelligence system for interconnection queue monitoring.
It ingests public or synthetic queue snapshots, preserves raw rows, normalizes messy project records,
links records into stable project entities across monthly snapshots, detects meaningful changes, computes
sample-aware historical proxy metrics, and generates citation-grounded public interconnection risk briefs.

The first version is designed for deterministic local demos and technical inspection. Fixture data is
synthetic but intentionally shaped like messy ERCOT GIS-style queue rows so tests and evals can run offline.

## What this project does not do

- It does not replace a formal interconnection study, deliverability study, power-flow result, or upgrade-cost estimate.
- It does not perform parcel-level siting, land diligence, permit submission, or proprietary development workflows.
- It does not claim queue outcomes that are unsupported by public source rows.
- It does not treat ERCOT generation queue records as a full data-center or large-load queue.
- It does not hide ambiguous entity matches behind a single forced answer.

## Domain safety and abstention rules

- Every important number in a generated brief must trace to a source, snapshot, structured query, or record citation.
- Rates must show `sample_n`, `fallback_level`, and confidence.
- If a sample is too small, the system rolls up to a broader scope; if still too small, it abstains.
- Missing public rows are not automatically treated as confirmed withdrawals unless status/source evidence supports that conclusion.
- Data center and large-load questions are caveated because the MVP ingests generation-resource queue records.
- Optional LLM polishing, if added later, may only rewrite deterministic content and may not add facts.

## MVP user flow

1. Run fixture ingestion.
2. Open the API and UI locally.
3. Choose market, fuel type, county, MW size, target COD year, and optional question.
4. Generate a Public Interconnection Risk Brief.
5. Inspect monthly diff events, entity match evidence, metric fallback, citations, and eval results.

