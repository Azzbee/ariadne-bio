.DEFAULT_GOAL := help
PYTHON ?= .venv/bin/python
COMPOSE ?= docker compose

.PHONY: help init install data evaluate ingest run docker-run docker-core docker-stop docker-logs test test-integration test-llm lint format notebook snapshot verify-scores audit-licenses benchmark-audits smoke clean

help: ## List reproducible project commands
	@awk 'BEGIN {FS = ":.*##"; printf "ARIADNE — trace evidence, challenge hypotheses\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-19s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

init: ## Create .env with a unique database password (never overwrites)
	python3 infra/init_env.py

install: ## Create a Python virtual environment and install pinned dependencies
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements-dev.txt

data: ## Download, checksum, prepare graph, train and evaluate the frozen model
	$(PYTHON) -m scripts.prepare_data
	$(PYTHON) -m scripts.evaluate

evaluate: ## Reproduce the fixed-seed held-out benchmark from prepared data
	$(PYTHON) -m scripts.evaluate

ingest: ## Idempotently import prepared evidence into the configured Neo4j service
	$(PYTHON) -m scripts.load_neo4j

run: init ## Run the API locally on http://localhost:8000 using local configuration
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env

docker-run: init ## Build and launch Neo4j, API, web UI and a local language model
	$(COMPOSE) --profile llm up --build --detach --wait --wait-timeout 1800 neo4j ollama
	@mkdir -p reports
	$(COMPOSE) --profile llm run --rm ollama-init > reports/ollama-model.json
	$(COMPOSE) --profile llm up --build --detach --wait --wait-timeout 1800 api frontend
	@echo "Open http://localhost:8080 and http://localhost:8080/docs"

docker-core: init ## Launch Neo4j, API and UI without downloading a language model
	$(COMPOSE) up --build --detach --wait --wait-timeout 1800
	@echo "Open http://localhost:8080 (agent mode is reported explicitly)"

docker-stop: ## Stop containers; retain downloaded graph and database volumes
	$(COMPOSE) --profile llm down

docker-logs: ## Follow application and database startup logs
	$(COMPOSE) logs --follow api neo4j frontend

test: ## Run unit/API tests and enforce at least 60% branch coverage
	$(PYTHON) -m pytest -m "not integration and not llm" --cov --cov-report=term-missing --cov-report=xml --junitxml=reports/junit.xml
	node --test frontend/tests/*.test.js

test-integration: ## Run genuine Neo4j/GDS integration tests against configured service
	$(PYTHON) -m pytest -m integration -v --junitxml=reports/neo4j-junit.xml

test-llm: ## Verify actual LLM inference, sensitivity routing and rejection over HTTP
	$(PYTHON) -m pytest -m llm -v --junitxml=reports/llm-junit.xml

lint: ## Enforce pylint score >=9.5 and formatting
	$(PYTHON) -m pylint app scripts --fail-under=9.5
	$(PYTHON) -m black --check app scripts tests infra

format: ## Format project Python source
	$(PYTHON) -m black app scripts tests infra

notebook: ## Execute the complete exploration notebook and save its outputs
	$(PYTHON) infra/run_notebook.py

snapshot: ## Export the frozen research edition for browser-only hosting
	$(PYTHON) -m scripts.export_snapshot

verify-scores: ## Compare every score with v1.0.0; requires that commit in local Git history
	$(PYTHON) -m scripts.verify_assessments

audit-licenses: ## Inventory observed data-license text; never grants commercial clearance
	$(PYTHON) -m scripts.audit_licenses

benchmark-audits: ## Audit all diseases' top ten against global binding-deletion budgets 0..2
	$(PYTHON) -m scripts.benchmark_audits --data-dir data/processed --output reports/v1.2.0/binding-audit-benchmark.json

smoke: ## Verify live HTTP evidence, audit certificates, tamper rejection and agent guard
	$(PYTHON) infra/smoke.py --base-url http://localhost:8080

clean: ## Remove reproducible caches and test outputs; preserve source and data
	$(PYTHON) infra/clean.py
