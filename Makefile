.PHONY: install run drills bench site test lint serve api all
PY := .venv/bin/python
install:   ## venv + package + dev tools + embedded PostgreSQL for local use
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev,local]"
run:       ## simulate 3 days, ingest, dbt, monitor (fresh database)
	$(PY) -m assembly run --days 3
drills:    ## fault-injection drills -> output/fault-drills.json
	$(PY) -m assembly drills
bench:     ## SQL benchmark on a simulated week -> output/benchmarks.json
	$(PY) -m assembly bench --days 7
site:      ## dashboard + dbt docs -> site/
	$(PY) -m assembly export && $(PY) -m assembly docs
serve:
	python3 -m http.server 8000 -d site
api:
	.venv/bin/uvicorn assembly.api:app --reload --app-dir src
test:
	.venv/bin/pytest --cov=assembly
lint:
	.venv/bin/ruff check src tests
all: drills run site
