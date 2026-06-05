# Data Sources

## ERCOT GIS Report

- URL: https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er
- Role: Primary generation interconnection queue source for ERCOT-oriented records.
- MVP status: Fixture ingestion works offline. Manual ERCOT GIS file ingestion is supported through `data/raw`.
- Caveat: ERCOT file layouts can change. GridQueue uses alias-based column mapping and stores raw payload JSON before normalization.

## ERCOT Large Load Update, April 9 2026

- URL: https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf
- Role: Public context for large-load and data-center questions.
- MVP status: Cited as context only.
- Caveat: It is not treated as a generation queue and does not create large-load queue rows in this MVP.

## LBNL Queued Up

- URL: https://emp.lbl.gov/queues
- Role: Future national benchmark source and fallback context.
- MVP status: Manual file ingestion path exists; deterministic fixture tests do not require LBNL files.
- Caveat: LBNL schemas and publication formats can vary, so automated ingestion is deliberately conservative.

## gridstatus interconnection queue docs

- URL: https://opensource.gridstatus.io/en/latest/interconnection_queues.html
- Role: Optional future ingestion adapter reference.
- MVP status: Documented but not required.

## FERC RM26-4 large-load interconnection docket

- URL: https://www.ferc.gov/rm26-4
- Role: Flexibility Strategy rule-status context for large-load interconnection reform.
- Phase 2 status: Seeded as pending/proposed ANOPR context, not final rule authority.
- Caveat: Does not support guaranteed benefits or quantified timeline savings.

## SPP High Impact Large Load integration

- URL: https://www.spp.org/markets-operations/high-impact-large-load-hill-integration/
- Role: Public SPP HILL/HILLGA/CHILL process context.
- Phase 2 status: Seeded as approved based on public SPP/FERC materials, but qualitative unless quantified benefit JSON
  is manually verified and seeded.
- Caveat: Seeded text is not a substitute for tariff review.

## FERC PJM co-located load fact sheet

- URL: https://www.ferc.gov/news-events/news/fact-sheet-ferc-directs-nations-largest-grid-operator-create-new-rules-embrace
- Role: Public context for directed PJM co-located load reforms.
- Phase 2 status: Seeded as directed/reform pending.
- Caveat: Not treated as final tariff terms.

## Emerald AI / EPRI DCFlex field demonstration

- URL: https://arxiv.org/html/2507.00909v1
- Role: Technical evidence anchor for compute-flexibility extrapolation checks.
- Phase 2 status: Seeded as `technical_evidence`.
- Caveat: It is not an ISO/RTO tariff or regulatory eligibility rule.

## Manual ingestion fallback

If automatic source download is blocked or a public website changes, use:

```powershell
python scripts/ingest_live_ercot.py data/raw/<ercot-file.xlsx>
python scripts/ingest_lbnl.py data/raw/<lbnl-file.xlsx>
```

The ingester records source metadata, file hash, snapshot date, row count, raw payload JSON, normalized records,
and record-level citations.
