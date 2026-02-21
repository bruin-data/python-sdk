.PHONY: setup build test test-unit test-integration test-duckdb test-bigquery test-snowflake lint format clean

setup:
	uv sync --extra dev --extra all

build:
	uv build

test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/ -v -m "not integration"

test-integration:
	uv run pytest tests/integration/ -v

test-duckdb:
	uv run pytest tests/integration/test_duckdb.py -v

test-bigquery:
	uv run pytest tests/integration/test_bigquery.py -v

test-snowflake:
	uv run pytest tests/integration/test_snowflake.py -v

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
