# Reviewer2 — developer tasks.
# Everything below runs fully OFFLINE and deterministically (no API keys) unless
# you opt into a cloud/local LLM provider via REVIEWER2_LLM_PROVIDER.

.DEFAULT_GOAL := help
.PHONY: help install sync demo demo-json eval test lint typecheck check mcp app clean

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install sync:  ## Create the venv and install core + dev deps (uv).
	uv sync --extra dev

demo:  ## Run Reviewer2 over the 3 bundled fixture cases (offline).
	uv run reviewer2 demo

demo-json:  ## Same as demo, but emit machine-readable JSON dossiers.
	uv run reviewer2 demo --json

eval:  ## Run the ErrorCatch harness and write eval/results/errorcatch.json.
	uv run python -m eval.errorcatch

test:  ## Run the test suite.
	uv run pytest

lint:  ## Lint with ruff.
	uv run ruff check .

typecheck:  ## Static type-check with mypy.
	uv run mypy src

check: lint test  ## Lint + test (the pre-commit bar).

mcp:  ## Start the MCP server (requires: uv sync --extra mcp).
	uv run python -m mcp_server.server

app:  ## Launch the Streamlit demo UI (requires: uv sync --extra app).
	uv run streamlit run app/streamlit_app.py

clean:  ## Remove caches and build artifacts.
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build **/__pycache__
	find . -name '*.pyc' -delete
