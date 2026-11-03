.DEFAULT_GOAL := help
PYTHON ?= .venv/bin/python
COMPOSE ?= docker compose
INTEGRATION ?= 0

.PHONY: help init install prepare-data data evaluate ingest run docker-run docker-core docker-stop docker-logs test test-integration test-llm test-browser lint format notebook notebook-refit snapshot verify-scores audit-licenses benchmark-audits benchmark-provenance benchmark-mixed benchmark-mixed-scaling provenance-controls package-release smoke clean

help: ## List reproducible project commands
	@awk 'BEGIN {FS = ":.*##"; printf "ARIADNE — trace evidence, challenge hypotheses\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-19s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

init: ## Create .env with a unique database password (never overwrites)
	python3 infra/init_env.py

install: ## Create a Python virtual environment and install pinned dependencies
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements-dev.txt

prepare-data: ## Prepare the checksummed graph without replacing the saved model or reports
	$(PYTHON) -m scripts.prepare_data

data: prepare-data ## Prepare graph, fit a new model and replace this checkout's evaluation
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
	$(COMPOSE) -f docker-compose.yml -f docker-compose.llm.yml --profile llm up --build --detach --wait --wait-timeout 1800 api frontend
	@echo "Open http://localhost:8080 and http://localhost:8080/docs"

docker-core: init ## Launch Neo4j, API and UI without downloading a language model
	$(COMPOSE) up --build --detach --wait --wait-timeout 1800
	@echo "Open http://localhost:8080 (agent mode is reported explicitly)"

docker-stop: ## Stop containers; retain downloaded graph and database volumes
	$(COMPOSE) --profile llm down

docker-logs: ## Follow application and database startup logs
	$(COMPOSE) logs --follow api neo4j frontend

test: snapshot ## Prepare recorded cases, then run unit/API/frontend tests; INTEGRATION=1 adds Neo4j/GDS
	$(PYTHON) -m pytest -m "not integration and not llm" --cov --cov-report=term-missing --cov-report=xml --junitxml=reports/junit.xml
	node --test frontend/tests/*.test.js
ifeq ($(INTEGRATION),1)
	$(MAKE) test-integration
endif

test-integration: ## Run genuine Neo4j/GDS integration tests against configured service
	ARIADNE_REQUIRE_NEO4J=1 $(PYTHON) -m pytest -m integration -v --junitxml=reports/neo4j-junit.xml

test-llm: ## Verify actual LLM inference, sensitivity routing and rejection over HTTP
	$(PYTHON) -m pytest -m llm -v --junitxml=reports/llm-junit.xml

test-browser: ## Run Chromium UI/API-reference checks; requires Python, npm ci, browser and snapshot
	ARIADNE_BROWSER_PYTHON="$(PYTHON)" npm --prefix frontend run browser:smoke

lint: ## Enforce pylint score >=9.5 and formatting
	$(PYTHON) -m pylint app scripts --fail-under=9.5
	$(PYTHON) -m black --check app scripts tests infra

format: ## Format project Python source
	$(PYTHON) -m black app scripts tests infra

notebook: ## Execute the notebook with prepared data and matching saved model/reports
	$(PYTHON) infra/run_notebook.py

notebook-refit: ## Refit, refresh both notebook benchmarks, then execute (replaces local results)
	$(MAKE) data
	$(MAKE) benchmark-audits benchmark-provenance
	$(MAKE) notebook

snapshot: prepare-data ## Export recorded browser cases with the saved model, without refitting
	$(PYTHON) -m scripts.export_snapshot

verify-scores: ## Compare every score with v1.0.0; requires that commit in local Git history
	$(PYTHON) -m scripts.verify_assessments

audit-licenses: ## Inventory observed data-license text; never grants commercial clearance
	$(PYTHON) -m scripts.audit_licenses

benchmark-audits: ## Audit all diseases' top ten against global binding-deletion budgets 0..2
	$(PYTHON) -m scripts.benchmark_audits --data-dir data/processed --output reports/v1.2.0/binding-audit-benchmark.json

benchmark-provenance: ## Audit correlated provider withdrawals and conditional protection plans
	$(PYTHON) -m scripts.benchmark_provenance --data-dir data/processed --output reports/v1.3.0/provenance-audit-benchmark.json

provenance-controls: ## Measure disclosed size-matched random controls for two illustrative cases
	$(PYTHON) -m scripts.provenance_controls --data-dir data/processed --output reports/v1.3.0/provenance-size-matched-controls.json

benchmark-mixed: ## Certify joint source and record withdrawals for every disease's top ten
	$(PYTHON) -m scripts.benchmark_mixed --data-dir data/processed --output reports/v1.4.0/mixed-audit-benchmark.json

benchmark-mixed-scaling: ## Compare exact envelopes and complete-world enumeration with cold caches
	$(PYTHON) -m scripts.benchmark_mixed_scaling --output-dir reports/v1.4.0/scaling

package-release: ## Package an explicit committed source ref and its matching research snapshot
	$(PYTHON) infra/package_release.py --ref $(or $(REF),HEAD) --output $(or $(OUTPUT),dist/release)

smoke: ## Verify live HTTP evidence, audit certificates, tamper rejection and agent guard
	$(PYTHON) infra/smoke.py --base-url http://localhost:8080

clean: ## Remove reproducible caches and test outputs; preserve source and data
	$(PYTHON) infra/clean.py
