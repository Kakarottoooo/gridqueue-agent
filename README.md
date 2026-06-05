# GridQueue Agent

GridQueue Agent is a local-first public-data intelligence system for interconnection queue monitoring. It ingests
public or synthetic queue snapshots, normalizes messy project records, resolves stable entities across monthly
snapshots, detects meaningful changes, computes sample-aware historical proxy metrics, and generates citation-grounded
Public Interconnection Risk Briefs.

It complements power-development platforms such as Paces by focusing on the public-data layer: queue monitoring,
change detection, historical benchmarking, source-grounded summaries, and automated quality checks. It does not copy
parcel-level siting, permitting, proprietary diligence, power-flow studies, or upgrade-cost modeling workflows.

## What it does not do

- It is not a formal interconnection study, deliverability study, power-flow result, or upgrade-cost estimate.
- It does not perform parcel siting, permitting, or proprietary development diligence.
- It does not treat ERCOT generation queue records as a full large-load or data-center queue.
- It does not report rates from samples that are too small; it rolls up or abstains.

## Architecture

```mermaid
graph TD
  A["Fixture or manual public files"] --> B["Ingestion service"]
  B --> C["Raw project records"]
  B --> D["Normalized project records"]
  D --> E["Entity resolution"]
  E --> F["Monthly diff events"]
  D --> G["Sample-aware metrics"]
  C --> H["Citations"]
  F --> I["Brief generator"]
  G --> I
  H --> I
  I --> J["FastAPI"]
  J --> K["Next.js UI"]
  D --> L["Deterministic eval runner"]
  E --> L
  F --> L
  G --> L
```

## Data sources

- ERCOT GIS Report: https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er
- ERCOT Large Load Update, April 9 2026: https://www.ercot.com/files/docs/2026/04/09/ERCOTLargeLoadUpdate-April9HouseStateAffairsHearing.pdf
- LBNL Queued Up: https://emp.lbl.gov/queues
- gridstatus queue docs: https://opensource.gridstatus.io/en/latest/interconnection_queues.html

The default demo uses synthetic fixtures under `data/fixtures`. They are clearly marked synthetic and are not market facts.

## Run locally

```powershell
make install
make ingest-fixtures
make test
make eval
make dev-api
make dev-web
```

Open the API docs at http://127.0.0.1:8000/docs and the web app at http://localhost:3000.
The frontend proxies `/api/backend/*` to `BACKEND_API_URL` and defaults to `http://127.0.0.1:8000`.
If port 8000 is occupied, start the API on another port and run the web app with `BACKEND_API_URL` set to that URL.

If `make` is unavailable on Windows, run the underlying commands:

```powershell
python -m pip install -e backend[dev]
cd frontend; npm install; cd ..
python scripts/ingest_fixture.py
python -m pytest backend/tests
python evals/run_evals.py
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
cd frontend; npm run dev
```

## Demo workflow

1. Click `Ingest fixtures` in the UI, or run `make ingest-fixtures`.
2. Use the default ERCOT, Battery, Reeves, 100 MW, 2028 input.
3. Click `Generate brief`.
4. Inspect the Brief, Monthly Diff, Metrics, Entity Matching, Citations, and Evals tabs.

## Entity resolution

The matcher is deterministic and explainable. It scores exact queue IDs, normalized name similarity, interconnecting
entity similarity, county/state, compatible fuel transitions, capacity tolerance, POI similarity, and target COD
proximity. Ambiguous top candidates are flagged and surfaced instead of forced.

See `docs/ENTITY_RESOLUTION.md`.

## Sample-aware rollups

Metrics follow this fallback path: county plus fuel type, county all fuels, market plus fuel type, market all fuels,
LBNL national fallback when available, then abstention. Every rate includes `sample_n`, `fallback_level`, and
confidence.

See `docs/METRICS_AND_ROLLUPS.md`.

## Evals

```powershell
make eval
```

Sample output:

```json
{
  "passed": 12,
  "failed": 0,
  "total": 12
}
```

Reports are generated at `evals/results/latest.json` and `evals/results/latest.md`.

## Manual public-data ingestion

```powershell
python scripts/ingest_live_ercot.py data/raw/<ercot-file.xlsx>
python scripts/ingest_lbnl.py data/raw/<lbnl-file.xlsx>
```

Calling those scripts without a file prints manual-download instructions.

## Tests and quality

- Backend: `python -m pytest backend/tests`
- Evals: `python evals/run_evals.py`
- Frontend typecheck: `cd frontend && npm run typecheck`
- Frontend lint: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`

## Demo screenshots

Screenshots are intentionally not committed. Run `make dev-api` and `make dev-web`, then open the app locally to
inspect the current fixture-backed demo.

## Known limitations

- Automatic ERCOT/LBNL download is not forced in the MVP; manual file ingestion is the supported public-data path.
- Fixture samples are small, so demo metric thresholds are lowered explicitly where needed.
- LBNL national benchmark fallback is represented in methodology but not populated by default fixtures.
- Entity resolution is deterministic and auditable, not a calibrated probabilistic model.

## Roadmap

- Add source-specific ERCOT and LBNL adapters after inspecting current downloaded files.
- Add reviewer workflow for ambiguous entity matches.
- Add market-specific threshold calibration.
- Add optional LLM polishing constrained to deterministic facts and citations.
- Add Docker Compose and hosted preview deployment.
