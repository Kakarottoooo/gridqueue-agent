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

## Manual ingestion fallback

If automatic source download is blocked or a public website changes, use:

```powershell
python scripts/ingest_live_ercot.py data/raw/<ercot-file.xlsx>
python scripts/ingest_lbnl.py data/raw/<lbnl-file.xlsx>
```

The ingester records source metadata, file hash, snapshot date, row count, raw payload JSON, normalized records,
and record-level citations.

