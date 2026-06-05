# GridQueue Agent Self-Audit

Audit date: 2026-06-05

## 1. Summary

Overall health: the project is credible as a GitHub/demo-ready public-data engineering portfolio project. The strongest
parts are deterministic entity resolution, stable-entity diffing, sample-aware metric rollups, citation-backed brief
payloads, and deterministic evals that exercise the core failure modes.

GitHub/demo readiness: ready after this audit, assuming reviewers understand the default data is synthetic fixture data
and live public ingestion is manual-file based. The app, backend tests, evals, frontend build, dependency audit, and
frontend-proxy smoke test all pass locally.

Biggest strengths:

- Entity resolution is not simple row diffing; it stores match score, method, feature evidence, and ambiguity flags.
- Monthly diffs operate on resolved entities and include explanations/confidence.
- Metrics show `sample_n`, `fallback_level`, and confidence, and abstain when samples are insufficient.
- Brief generation is deterministic, source-aware, caveated, and includes reproducibility trace metadata.
- CI now runs backend tests, evals, frontend audit, typecheck, lint, and production build with fixture data only.

Biggest remaining risks:

- Live ingestion is limited to manual ERCOT/LBNL file inputs; the MVP does not guarantee automatic download from public
  portals.
- Fixture data is synthetic and intentionally small, so it demonstrates behavior rather than market truth.
- Entity-resolution weights are deterministic and explainable, but not calibrated against a large real-world benchmark.
- The smoke test validates the rendered shell and frontend proxy endpoint, not a full browser click-through session.

## 2. Commands Run

Unless noted, commands were run from the repository root.

| Command | Result | Notes |
| --- | --- | --- |
| `python -m pytest backend/tests` | Pass | 10 passed after the citation/eval hardening. |
| `python evals/run_evals.py` | Pass | 12/12 passed after stricter brief-provenance checks. |
| `cd frontend; npm install` | Pass | Dependencies already up to date, 0 vulnerabilities reported. |
| `cd frontend; npm run typecheck` | Pass | TypeScript completed with no errors. |
| `cd frontend; npm run lint` | Pass | ESLint completed with no errors. |
| `cd frontend; npm audit --audit-level=moderate` | Pass | 0 vulnerabilities. |
| `cd frontend; npm run build` | Pass | Next.js production build completed; `/api/backend/[...path]` remains dynamic. |
| `rg -n "C:\\\\Users\\\\\|OPENAI_API_KEY=.*\\S\|gho_[A-Za-z0-9]+\|sk-(proj\|live\|test\|[A-Za-z0-9]{20,})\|api[_-]?key\\s*=\|password\\s*=\|secret\\s*=\|token\\s*=" -S --glob "!frontend/node_modules/**" --glob "!frontend/.next/**" --glob "!docs/SELF_AUDIT.md" .` | Pass | No committed secrets, local absolute paths, or non-empty API keys were found. The audit file was excluded so the command pattern does not match itself. |
| `git ls-files \| rg "(^|/)(node_modules|\\.next|data/raw|data/processed|evals/results)/|\\.duckdb$|\\.env$|\\.tsbuildinfo$"` | Pass | Only expected `.gitkeep` files under ignored generated-data directories were tracked. |
| `Test-Path -LiteralPath .github/workflows/ci.yml` | Pass | CI workflow exists. |

App smoke test:

- Ports `8000` and `3000` were already occupied locally, so the final passing smoke used FastAPI on `8013` and Next.js
  on `3013`.
- Equivalent command sequence:

```powershell
python scripts/ingest_fixture.py
$env:GRIDQUEUE_DB_PATH = "data/processed/gridqueue.duckdb"
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8013

cd frontend
$env:BACKEND_API_URL = "http://127.0.0.1:8013"
npm run start -- --port 3013

Invoke-WebRequest http://localhost:3013
Invoke-RestMethod -Method Post http://localhost:3013/api/backend/brief -ContentType application/json -Body '{...}'
```

Final smoke result:

```json
{
  "api": "http://127.0.0.1:8013",
  "frontend": "http://localhost:3013",
  "title": "Public Interconnection Risk Brief",
  "snapshot_id": "snap_ercot_2026_02_28",
  "comparable_count": 3,
  "citation_count": 4,
  "sample_n": 3,
  "fallback_level": "county_fuel",
  "confidence": "Low"
}
```

Two smoke-wrapper attempts failed before the final pass due to Windows PowerShell scripting issues: duplicate stdout and
stderr redirect targets in `Start-Process`, then accidental assignment to the read-only `$HOME` variable via `$home`.
Those were wrapper defects, not app defects.

## 3. Issues Found

### High - CI - Missing GitHub Actions

Description: the repository had no CI workflow, so reviewers had to trust local commands.

Fix applied: added `.github/workflows/ci.yml` with two fixture-only jobs: backend tests/evals and frontend
audit/typecheck/lint/build.

### Medium - Brief generation - Comparable projects lacked direct citation IDs

Description: the brief cited the latest queue snapshot and included record citations globally, but comparable projects
were emitted with empty `citation_ids`. That weakened the claim that key brief records are source-backed.

Fix applied: `generate_brief` now attaches record-level citation IDs to each top comparable project and includes those
citations in the response.

### Medium - Evals/tests - Citation eval was too shallow

Description: the `brief-citations` eval only checked that some citations existed and that the snapshot had citation IDs.
It would not fail if comparable citations disappeared.

Fix applied: strengthened backend tests and evals to require snapshot citations, comparable-project citation IDs, source
URLs, and historical proxy metadata (`sample_n`, `fallback_level`, `confidence`).

### Medium - Docs - Machine-specific path in decision record

Description: `docs/DECISIONS.md` contained a local absolute checkout path. That looks accidental in a public repo.

Fix applied: replaced the machine-specific path with generic root-directory wording.

### Low - Backend/setup - CORS origins were fixed in code

Description: the backend allowed a few localhost ports directly in code. That is acceptable for a local demo, but brittle
when the frontend uses fallback ports.

Fix applied: added `GRIDQUEUE_CORS_ORIGINS` parsing in backend config and documented it in `.env.example` and README.
The bundled Next.js proxy still avoids most direct CORS needs.

### Low - Docs/setup - Dependency audit command missing from README quality section

Description: README listed tests, evals, typecheck, lint, and build, but not the dependency audit command used in this
review.

Fix applied: added `cd frontend && npm audit --audit-level=moderate`.

### Low - App smoke - Default local ports were occupied

Description: local ports `8000` and `3000` were already in use during review.

Fix applied: no code change needed. README already describes fallback API ports through `BACKEND_API_URL`; this audit
documents the exact fallback smoke ports used.

## 4. Changes Made

- `.github/workflows/ci.yml`: adds CI for backend tests, deterministic evals, frontend dependency audit, typecheck,
  lint, and production build.
- `backend/app/config.py`: adds `GRIDQUEUE_CORS_ORIGINS` parsing and default localhost allowlist.
- `backend/app/main.py`: uses backend config for CORS origins instead of inline constants.
- `backend/app/services/brief_generation/generator.py`: attaches record-level citation IDs to comparable projects.
- `backend/tests/test_pipeline.py`: asserts brief citations cover snapshot and comparable projects and that historical
  proxy metadata is present.
- `evals/run_evals.py`: strengthens the `brief-citations` case so provenance regressions fail evals.
- `.env.example`: documents configurable CORS origins.
- `README.md`: documents direct API CORS configuration and the npm audit command.
- `docs/DECISIONS.md`: removes a local absolute path.
- `docs/SELF_AUDIT.md`: records the audit, fixes, verification commands, and remaining limitations.

These changes improve credibility because they make the repo easier to verify from a clean checkout, reduce public-repo
polish issues, and force future changes to preserve citation/provenance guarantees.

## 5. Remaining Limitations

- Public live ingestion remains manual-file based; automatic ERCOT/LBNL downloads are intentionally not guaranteed in
  this MVP.
- Default fixture data is synthetic. It proves pipeline behavior, not real ERCOT queue facts.
- The LBNL national fallback path is documented as methodology but not populated by default fixtures.
- The entity resolver is deterministic and auditable, but weights are not statistically calibrated.
- Ambiguous matches are surfaced, but there is no reviewer adjudication workflow yet.
- The app smoke validates the shell and frontend proxy endpoint. It does not automate all UI tabs with browser clicks.
- The project does not estimate deliverability, actual grid capacity, upgrade cost, approval probability, or formal
  interconnection-study outcomes.

## 6. Reviewer Notes

A Paces-like engineering manager should notice that this project is strongest where shallow demos usually fail:
identity over time, explainable diffing, sample-size honesty, and source grounding.

Entity resolution uses a deterministic weighted matcher across queue ID, normalized name, interconnecting entity,
county/state, fuel compatibility, capacity tolerance, POI similarity, and target COD proximity. It stores
`match_score`, `match_method`, `match_features_json`, and `is_ambiguous`, and the UI exposes match trace/ambiguity
instead of hiding it.

Rollups are deliberately conservative. The system tries county plus fuel type, county all fuels, market plus fuel type,
market all fuels, LBNL fallback when populated, then abstention. The brief always shows `sample_n`, `fallback_level`, and
confidence, which is more credible than reporting precise rates from tiny samples.

Brief generation is deterministic and should be read as a public-data signal summary. It includes the formal-study
caveat, does not claim grid deliverability or upgrade-cost knowledge, and treats data-center/large-load questions as
separate public context rather than pretending generation queue records are a full large-load queue.
