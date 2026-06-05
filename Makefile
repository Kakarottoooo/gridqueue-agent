.PHONY: install ingest-fixtures ingest-live-ercot ingest-lbnl seed-flex-rules seed-watch-sources run-watcher seed-lead-time-kb seed-time-to-power-fixtures time-to-power-demo real-ercot-profile real-ercot-run real-lbnl-profile real-lbnl-reproduce real-eval real-validation-report flex-demo watcher-demo counts test eval dev-api dev-web demo frontend-typecheck frontend-lint

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

seed-time-to-power-fixtures:
	python scripts/seed_time_to_power_fixtures.py

time-to-power-demo:
	python scripts/run_time_to_power_demo.py

real-ercot-profile:
	python scripts/profile_real_ercot_gis.py

real-ercot-run:
	python scripts/run_real_ercot_pair.py --from-file data/raw/real/ercot/gis/ERCOT_GIS_2026_04.xlsx --from-snapshot-date 2026-04-30 --to-file data/raw/real/ercot/gis/ERCOT_GIS_2026_05.xlsx --to-snapshot-date 2026-05-31

real-lbnl-profile:
	python scripts/profile_real_lbnl_workbook.py --file data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx

real-lbnl-reproduce:
	python scripts/run_lbnl_reproduction.py --file data/raw/real/lbnl/LBNL_Queued_Up_2026_Data_File.xlsx

real-eval:
	python evals/run_real_evals.py

real-validation-report:
	python scripts/generate_real_data_validation_report.py

flex-demo:
	python scripts/ingest_fixture.py
	python scripts/seed_flexibility_rules.py

watcher-demo:
	python scripts/ingest_fixture.py
	python scripts/seed_flexibility_rules.py
	python scripts/seed_watch_sources.py
	python scripts/run_monthly_watcher.py --mode fixture --period 2026-05
	python scripts/seed_lead_time_kb.py
	python scripts/seed_time_to_power_fixtures.py

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
