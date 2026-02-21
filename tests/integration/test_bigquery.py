"""Integration tests for BigQuery using real GCP credentials.

Skipped automatically when ``BRUIN_TEST_BQ_PROJECT_ID`` is absent.

Required env vars::

    BRUIN_TEST_BQ_PROJECT_ID              – GCP project with BigQuery enabled

Optional env vars::

    BRUIN_TEST_BQ_SERVICE_ACCOUNT_JSON    – service-account JSON string
                                            (falls back to ADC if absent)

BigQuery detection uses ``job.result().schema``: non-empty for SELECT,
empty for DDL/DML.
"""

import os
import uuid

import pandas as pd
import pytest

from bruin import query
from tests.integration.conftest import requires_bigquery

pytestmark = requires_bigquery


@pytest.fixture
def _test_table(bq_env):
    """Yield a unique fully-qualified table name and drop it after the test."""
    project = os.environ["BRUIN_TEST_BQ_PROJECT_ID"]
    table = f"{project}._bruin_sdk_test.integ_{uuid.uuid4().hex[:8]}"
    yield table
    try:
        query(f"DROP TABLE IF EXISTS `{table}`", "test_bq")
    except Exception:
        pass  # best-effort cleanup


@pytest.fixture(autouse=True)
def _ensure_dataset(bq_env):
    """Create the scratch dataset if it doesn't exist (idempotent)."""
    project = os.environ["BRUIN_TEST_BQ_PROJECT_ID"]
    try:
        query(
            f"CREATE SCHEMA IF NOT EXISTS `{project}._bruin_sdk_test`",
            "test_bq",
        )
    except Exception:
        pass  # may already exist or lack permissions — tests will fail clearly


class TestBigQuerySelect:
    def test_simple_select(self, bq_env):
        result = query("SELECT 1 AS id, 'hello' AS name", "test_bq")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]
        assert len(result) == 1

    def test_multi_row(self, bq_env):
        result = query(
            "SELECT * FROM UNNEST([1, 2, 3]) AS x",
            "test_bq",
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    def test_cte_select(self, bq_env):
        result = query(
            "WITH cte AS (SELECT 1 AS x UNION ALL SELECT 2) SELECT * FROM cte",
            "test_bq",
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2


class TestBigQueryDDL:
    def test_create_table_returns_none(self, _test_table):
        result = query(
            f"CREATE TABLE `{_test_table}` (id INT64, name STRING)",
            "test_bq",
        )
        assert result is None

    def test_drop_table_returns_none(self, _test_table):
        query(f"CREATE TABLE `{_test_table}` (id INT64)", "test_bq")
        result = query(f"DROP TABLE `{_test_table}`", "test_bq")
        assert result is None


class TestBigQueryDML:
    def test_insert_returns_none(self, _test_table):
        query(f"CREATE TABLE `{_test_table}` (id INT64)", "test_bq")
        result = query(
            f"INSERT INTO `{_test_table}` (id) VALUES (1), (2)",
            "test_bq",
        )
        assert result is None
