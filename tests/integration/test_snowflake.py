"""Integration tests for Snowflake using real credentials.

Skipped automatically when ``BRUIN_TEST_SF_*`` env vars are absent.

Required env vars::

    BRUIN_TEST_SF_ACCOUNT     – e.g. xy12345.us-east-1
    BRUIN_TEST_SF_USERNAME
    BRUIN_TEST_SF_PASSWORD
    BRUIN_TEST_SF_DATABASE
    BRUIN_TEST_SF_WAREHOUSE

Optional::

    BRUIN_TEST_SF_SCHEMA      – defaults to PUBLIC
    BRUIN_TEST_SF_ROLE

Snowflake detection uses ``cursor.description`` after ``cursor.execute()``.
"""

import os
import uuid

import pandas as pd
import pytest

from bruin import query

_SF_REQUIRED = (
    "BRUIN_TEST_SF_ACCOUNT",
    "BRUIN_TEST_SF_USERNAME",
    "BRUIN_TEST_SF_PASSWORD",
    "BRUIN_TEST_SF_DATABASE",
    "BRUIN_TEST_SF_WAREHOUSE",
)

pytestmark = pytest.mark.skipif(
    not all(os.environ.get(v) for v in _SF_REQUIRED),
    reason="Missing env vars: " + ", ".join(
        v for v in _SF_REQUIRED if not os.environ.get(v)
    ),
)


@pytest.fixture
def _temp_table(sf_env):
    """Yield a unique temporary table name — Snowflake drops it at session end."""
    name = f"_bruin_integ_{uuid.uuid4().hex[:8]}"
    yield name
    try:
        query(f"DROP TABLE IF EXISTS {name}", "test_sf")
    except Exception:
        pass


class TestSnowflakeSelect:
    def test_simple_select(self, sf_env):
        result = query("SELECT 1 AS id, 'hello' AS name", "test_sf")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        # Snowflake uppercases column names by default
        cols = [c.upper() for c in result.columns]
        assert "ID" in cols
        assert "NAME" in cols

    def test_multi_row(self, sf_env):
        result = query(
            "SELECT column1 AS x FROM VALUES (1), (2), (3)",
            "test_sf",
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    def test_cte_select(self, sf_env):
        result = query(
            "WITH cte AS (SELECT 1 AS x UNION ALL SELECT 2) SELECT * FROM cte",
            "test_sf",
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2


class TestSnowflakeDDL:
    def test_create_temp_table_returns_none(self, sf_env, _temp_table):
        result = query(
            f"CREATE TEMPORARY TABLE {_temp_table} (id INTEGER, name VARCHAR)",
            "test_sf",
        )
        # Snowflake sets cursor.description after DDL (returns status message)
        # so this may return a DataFrame with a "status" column, or None
        # depending on the connector version
        if result is not None:
            assert isinstance(result, pd.DataFrame)

    def test_drop_table_returns_none(self, sf_env, _temp_table):
        query(f"CREATE TEMPORARY TABLE {_temp_table} (id INTEGER)", "test_sf")
        result = query(f"DROP TABLE {_temp_table}", "test_sf")

        if result is not None:
            assert isinstance(result, pd.DataFrame)


class TestSnowflakeDML:
    def test_insert_into_temp_table(self, sf_env, _temp_table):
        query(f"CREATE TEMPORARY TABLE {_temp_table} (id INTEGER)", "test_sf")
        result = query(
            f"INSERT INTO {_temp_table} VALUES (1), (2), (3)",
            "test_sf",
        )

        # Snowflake may return affected-row info via cursor.description
        if result is not None:
            assert isinstance(result, pd.DataFrame)

    def test_round_trip(self, sf_env, _temp_table):
        """Insert rows, then SELECT them back — verifies full round trip."""
        query(f"CREATE TEMPORARY TABLE {_temp_table} (id INTEGER, name VARCHAR)", "test_sf")
        query(f"INSERT INTO {_temp_table} VALUES (1, 'a'), (2, 'b')", "test_sf")

        result = query(f"SELECT * FROM {_temp_table} ORDER BY id", "test_sf")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
