.PHONY: install ingest-fixtures ingest-live-ercot ingest-lbnl seed-flex-rules seed-watch-sources run-watcher seed-lead-time-kb flex-demo watcher-demo counts test eval dev-api dev-web demo frontend-typecheck frontend-lint

install:
	python -m pip install -e "backend[dev]"
	cd frontend && npm install

ingest-fixtures:
	python scripts/ingest_fixture.py

ingest-live-ercot:
	python scripts/ingest_live_ercot.py

ingest-lbnl:
	python scripts/ingest_lbnl.py

seed-flex-rules:
	python scripts/seed_flexibility_rules.py

seed-watch-sources:
	python scripts/seed_watch_sources.py

run-watcher:
	python scripts/run_monthly_watcher.py --mode fixture --period 2026-05

seed-lead-time-kb:
	python scripts/seed_lead_time_kb.py

flex-demo:
	python scripts/ingest_fixture.py
	python scripts/seed_flexibility_rules.py

watcher-demo:
	python scripts/ingest_fixture.py
	python scripts/seed_flexibility_rules.py
	python scripts/seed_watch_sources.py
	python scripts/run_monthly_watcher.py --mode fixture --period 2026-05
	python scripts/seed_lead_time_kb.py

counts:
	python scripts/print_counts.py

test:
	python -m pytest backend/tests

eval:
	python evals/run_evals.py

frontend-typecheck:
	cd frontend && npm run typecheck

frontend-lint:
	cd frontend && npm run lint

dev-api:
	python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload

dev-web:
	cd frontend && npm run dev

demo:
	python scripts/run_demo.py
