.PHONY: install test test-live lint typecheck clean ui ui-backend ui-frontend ui-install ui-test-smoke

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

install:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest -m "not live"

test-live:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy coordinator enablement_agents

clean:
	rm -rf .pytest_cache __pycache__ .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	rm -rf agent-state/*

# ---------------------------------------------------------------------------
# UI (scope expansion beyond v1 — see ui/README.md)
# ---------------------------------------------------------------------------

ui-install:
	$(PIP) install -e ".[ui]"
	cd ui/web && npm install
	cd ui/web && npx playwright install chromium

ui-backend:
	@if [ -f .env ]; then \
		echo "loading .env into uvicorn..."; \
		.venv/bin/uvicorn ui.api.server:app --reload --port 8000 --env-file .env; \
	else \
		echo "(no .env found — running with current shell env only)"; \
		.venv/bin/uvicorn ui.api.server:app --reload --port 8000; \
	fi

ui-frontend:
	cd ui/web && npm run dev

# Smoke-test the UI end-to-end. Playwright boots the FastAPI backend AND the
# Next.js dev server itself (see ui/web/playwright.config.ts), so do NOT run
# `make ui-backend` / `make ui-frontend` first — they'll port-conflict.
# Demo mode is forced on the backend; no LLM cost.
ui-test-smoke:
	cd ui/web && npx playwright test

# Convenience target: prints the two-terminal instructions. Running both
# servers in a single make process is fragile (they need to stay foregrounded
# in their own terminals so reload works and the user sees logs).
ui:
	@echo "The UI is two-tier. Run each command in its own terminal:"
	@echo "  Terminal 1:  make ui-backend"
	@echo "  Terminal 2:  make ui-frontend"
	@echo "Then open http://localhost:3000"
	@echo ""
	@echo "First-time setup:  make ui-install"
