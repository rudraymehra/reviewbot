# Code Review Copilot — common dev tasks.
# Usage: `make <target>`. Run `make help` to list everything.

VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help venv install test doctor dashboard serve clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv: ## Create the virtualenv if missing
	@test -d $(VENV) || python3 -m venv $(VENV)

install: venv ## Install the package + dev deps (editable)
	$(PIP) install -q -e ".[dev]"

test: ## Run the test suite
	$(VENV)/bin/pytest -q

doctor: ## Check local config & credentials are ready
	$(VENV)/bin/copilot doctor

dashboard: ## Launch the Streamlit dashboard
	$(VENV)/bin/streamlit run dashboard/app.py

serve: ## Run the webhook server on :8000
	$(VENV)/bin/copilot serve --port 8000

clean: ## Remove caches and build artifacts (keeps .venv and copilot.db)
	rm -rf .pytest_cache **/__pycache__ src/*.egg-info
	find . -name '*.pyc' -delete
