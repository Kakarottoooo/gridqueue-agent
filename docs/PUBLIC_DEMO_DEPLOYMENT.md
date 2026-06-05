# Public Demo Deployment

This is the smallest credible way to make GridQueue testable by other people without turning it into a full SaaS.

## What the public demo includes

- A hosted Next.js UI.
- A hosted FastAPI backend.
- Deterministic fixture data seeded at backend startup.
- Working flows for queue briefs, flexibility briefs, watcher digests, and time-to-power briefs.
- Links back to the real-data validation reports committed in GitHub.

## What the public demo does not include yet

- User accounts.
- Paid-plan uptime guarantees.
- Uploading arbitrary source workbooks.
- Scheduled live source refresh.
- Production abuse/rate limiting.
- A persistent customer workspace.

The real ERCOT and LBNL raw XLSX files are intentionally ignored by git. Public readers should inspect the committed
hashes, row counts, source traces, and generated reports instead of expecting those raw files in the repo.

## Deploy with Render

The repository includes `render.yaml`, a Render Blueprint with two services:

- `gridqueue-api`: FastAPI backend.
- `gridqueue-web`: Next.js frontend.

Steps:

1. Merge the deployment branch into the branch you want Render to deploy.
2. In Render, create a new Blueprint from `https://github.com/Kakarottoooo/gridqueue-agent`.
3. Use the repository root `render.yaml`.
4. Let Render create both services.
5. Open the web service URL and test:
   - Ingest fixtures.
   - Generate a deterministic queue brief.
   - Generate a flexibility brief.
   - Generate a watcher digest.
   - Generate a time-to-power brief.
6. Open the API health endpoint:
   - `https://<api-service>.onrender.com/health`
   - `https://<api-service>.onrender.com/docs`

If you rename the services, update the web service backend configuration. The frontend proxy supports either:

- `BACKEND_API_URL=https://<api-service>.onrender.com`
- or Render service references via `BACKEND_API_HOST` and `BACKEND_API_PORT`.

## Launch copy links

Use the repo URL as the technical proof link:

`https://github.com/Kakarottoooo/gridqueue-agent`

Use the hosted web URL as the user-test link after deployment:

`https://<web-service>.onrender.com`

Use the real evidence links for credibility:

- `docs/REAL_DATA_VALIDATION.md`
- `reports/real_data/ercot/real_monthly_digest_2026_04_to_2026_05.md`
- `reports/real_data/entity_resolution_audit/ercot_matches_2026_04_to_2026_05.csv`
- `reports/real_data/lbnl/lbnl_reproduction.md`

## Next step toward a real service

After the public demo gets inbound interest, the next build should be:

- A read-only public evidence page for the latest monthly digest.
- Email capture linked from the UI.
- Basic authentication for private watchlists.
- Persistent database or object storage.
- A background refresh job for supported public sources.
- Rate limiting before allowing arbitrary user-triggered ingestion.
