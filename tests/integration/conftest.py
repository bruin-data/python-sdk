"""Shared fixtures and skip helpers for integration tests.

These tests hit real database drivers (and optionally real cloud services).
They are marked ``@pytest.mark.integration`` automatically.

Run them with::

    pytest -m integration                     # all integration tests
    pytest tests/integration/                 # same, by directory
    pytest -m "not integration"               # skip them

DuckDB tests run locally (no credentials needed).
BigQuery and Snowflake tests require environment variables — they skip
gracefully when the variables are absent.
"""

import json
import os

import pytest


# ---------------------------------------------------------------------------
# Auto-apply the integration marker to every test collected in this directory
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(items):
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


# ---------------------------------------------------------------------------
# DuckDB  (no credentials needed — always available if duckdb is installed)
# ---------------------------------------------------------------------------

@pytest.fixture
def duckdb_env(monkeypatch):
    """Set up a DuckDB :memory: connection via bruin env vars."""
    pytest.importorskip("duckdb")
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"test_duck": "duckdb"}),
    )
    monkeypatch.setenv("test_duck", json.dumps({"path": ":memory:"}))


# ---------------------------------------------------------------------------
# BigQuery  (requires real GCP credentials)
# ---------------------------------------------------------------------------

@pytest.fixture
def bq_env(monkeypatch):
    """Set up a BigQuery connection from ``BRUIN_TEST_BQ_*`` env vars.

    Only ``BRUIN_TEST_BQ_PROJECT_ID`` is required.  When
    ``BRUIN_TEST_BQ_SERVICE_ACCOUNT_JSON`` is absent the SDK falls back
    to Application Default Credentials (``gcloud auth application-default login``).
    """
    project_id = os.environ["BRUIN_TEST_BQ_PROJECT_ID"]
    sa_json = os.environ.get("BRUIN_TEST_BQ_SERVICE_ACCOUNT_JSON", "")

    conn_payload = {"project_id": project_id}
    if sa_json:
        conn_payload["service_account_json"] = sa_json

    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"test_bq": "google_cloud_platform"}),
    )
    monkeypatch.setenv("test_bq", json.dumps(conn_payload))


# ---------------------------------------------------------------------------
# Snowflake  (requires real Snowflake credentials)
# ---------------------------------------------------------------------------

@pytest.fixture
def sf_env(monkeypatch):
    """Set up a Snowflake connection from ``BRUIN_TEST_SF_*`` env vars."""
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"test_sf": "snowflake"}),
    )
    monkeypatch.setenv("test_sf", json.dumps({
        "account": os.environ["BRUIN_TEST_SF_ACCOUNT"],
        "username": os.environ["BRUIN_TEST_SF_USERNAME"],
        "password": os.environ["BRUIN_TEST_SF_PASSWORD"],
        "database": os.environ["BRUIN_TEST_SF_DATABASE"],
        "warehouse": os.environ["BRUIN_TEST_SF_WAREHOUSE"],
        "schema": os.environ.get("BRUIN_TEST_SF_SCHEMA", "PUBLIC"),
        "role": os.environ.get("BRUIN_TEST_SF_ROLE", ""),
    }))
