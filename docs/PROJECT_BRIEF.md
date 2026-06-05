# GridQueue Agent Project Brief

GridQueue Agent is a local-first public-data intelligence system for interconnection queue monitoring.
It ingests public or synthetic queue snapshots, preserves raw rows, normalizes messy project records,
links records into stable project entities across monthly snapshots, detects meaningful changes, computes
sample-aware historical proxy metrics, and generates citation-grounded public interconnection risk briefs.

The first version is designed for deterministic local demos and technical inspection. Fixture data is
synthetic but intentionally shaped like messy ERCOT GIS-style queue rows so tests and evals can run offline.

Phase 2 adds a Flexibility Strategy Layer for large-load planning. It evaluates public FERC/ISO/RTO rule status,
curtailable-load eligibility, compute-side curtailment cost, and whether any interconnection benefit should be treated
as quantified, qualitative, contingent, unsupported, or abstained.

Phase 3 adds a Monthly Regulatory + Queue Change Watcher that turns queue diffs, curated regulatory source diffs, and
flexibility-rule records into a ranked "what changed?" digest. It also adds a conservative Post-NTP Lead-Time scaffold
for one equipment class, Large Power Transformers.

Phase 4 adds a Time-to-Power Brief that connects the GridQueue baseline, Flexibility Strategy Layer, and Post-NTP
Lead-Time scaffold into one range-based planning artifact. It estimates serial and at-risk-overlap energization
timelines from public-data proxies, explicit assumptions, citations, and caveats.

## What this project does not do

- It does not replace a formal interconnection study, deliverability study, power-flow result, or upgrade-cost estimate.
- It does not perform parcel-level siting, land diligence, permit submission, or proprietary development workflows.
- It does not claim queue outcomes that are unsupported by public source rows.
- It does not treat ERCOT generation queue records as a full data-center or large-load queue.
- It does not hide ambiguous entity matches behind a single forced answer.
- It does not execute load curtailment, schedule GPU workloads, provide legal/financial advice, or guarantee that a
  flexible load will receive faster approval.
- It does not fabricate monthly watcher changes when source parsing fails or entity matching is ambiguous.
- It does not provide procurement quotes, prices, OEM rankings, RFQ workflow, or guaranteed lead times.
- It does not provide a guaranteed Time-to-Power date, engineering design, OEM RFQ, commissioning plan, financial
  forecast, or guarantee of energization.

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
6. Optionally seed flexibility rules and generate a Flexibility Strategy Brief for a large-load curtailment scenario.
7. Optionally seed watcher sources and generate a Monthly Watcher digest.
8. Optionally seed the Large Power Transformer lead-time KB scaffold and inspect cited range rows.
9. Optionally seed Time-to-Power fixtures and generate a complete Time-to-Power Brief.
