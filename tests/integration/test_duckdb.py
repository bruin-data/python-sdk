"""Integration tests for DuckDB using a real :memory: connection.

These verify the actual cursor.description behavior after the SQL-parsing
removal.  No external credentials are needed — only the ``duckdb`` package.

Key finding: DuckDB sets ``result.description`` for *every* statement type
(SELECT, DDL, DML).  This means ``_execute()`` always returns a DataFrame
for DuckDB — DDL returns an empty DataFrame, DML returns a single-row
DataFrame with the affected row count.  This is accurate driver behavior
and differs from the old regex approach which returned None for non-SELECT.
"""

import pandas as pd
import pytest

from bruin import get_connection, query

pytest.importorskip("duckdb")


class TestDuckDBSelect:
    @pytest.fixture(autouse=True)
    def _setup(self, duckdb_env):
        pass

    def test_simple_select(self):
        result = query("SELECT 1 AS id, 'hello' AS name", "test_duck")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]
        assert len(result) == 1
        assert result["id"].iloc[0] == 1
        assert result["name"].iloc[0] == "hello"

    def test_multi_row_select(self):
        result = query(
            "SELECT * FROM (VALUES (1, 'a'), (2, 'b'), (3, 'c')) AS t(id, name)",
            "test_duck",
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert list(result.columns) == ["id", "name"]

    def test_cte_select(self):
        result = query(
            "WITH cte AS (SELECT 1 AS x UNION ALL SELECT 2) SELECT * FROM cte",
            "test_duck",
        )

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["x"]
        assert len(result) == 2

    def test_empty_result_set(self):
        """A SELECT that returns 0 rows still produces a DataFrame with columns."""
        conn = get_connection("test_duck")
        conn.query("CREATE TABLE empty_t (id INTEGER, name VARCHAR)")
        result = conn.query("SELECT * FROM empty_t")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]
        assert len(result) == 0

    def test_multiple_column_types(self):
        result = query(
            "SELECT 42 AS int_col, 3.14 AS float_col, 'txt' AS str_col, TRUE AS bool_col",
            "test_duck",
        )

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["int_col", "float_col", "str_col", "bool_col"]


class TestDuckDBDDL:
    """DuckDB returns a description for DDL — so the SDK returns a DataFrame, not None.

    CREATE/ALTER return an empty DataFrame (``Count`` column, 0 rows).
    DROP returns an empty DataFrame (``Success`` column, 0 rows).
    This is accurate DuckDB driver behavior.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, duckdb_env):
        pass

    def test_create_table(self):
        conn = get_connection("test_duck")
        result = conn.query("CREATE TABLE t (id INTEGER, name VARCHAR)")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0  # empty DataFrame

    def test_drop_table(self):
        conn = get_connection("test_duck")
        conn.query("CREATE TABLE t (id INTEGER)")
        result = conn.query("DROP TABLE t")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0  # empty DataFrame


class TestDuckDBDML:
    """DuckDB returns a ``Count`` column for DML showing affected rows."""

    @pytest.fixture(autouse=True)
    def _setup(self, duckdb_env):
        pass

    def test_insert_returns_count(self):
        conn = get_connection("test_duck")
        conn.query("CREATE TABLE t (id INTEGER)")
        result = conn.query("INSERT INTO t VALUES (1), (2), (3)")

        assert isinstance(result, pd.DataFrame)
        assert "Count" in result.columns
        assert result["Count"].iloc[0] == 3

    def test_update_returns_count(self):
        conn = get_connection("test_duck")
        conn.query("CREATE TABLE t (id INTEGER, val INTEGER)")
        conn.query("INSERT INTO t VALUES (1, 10), (2, 20)")
        result = conn.query("UPDATE t SET val = 99 WHERE id = 1")

        assert isinstance(result, pd.DataFrame)
        assert "Count" in result.columns
        assert result["Count"].iloc[0] == 1

    def test_delete_returns_count(self):
        conn = get_connection("test_duck")
        conn.query("CREATE TABLE t (id INTEGER)")
        conn.query("INSERT INTO t VALUES (1), (2), (3)")
        result = conn.query("DELETE FROM t WHERE id <= 2")

        assert isinstance(result, pd.DataFrame)
        assert "Count" in result.columns
        assert result["Count"].iloc[0] == 2


class TestDuckDBAnnotation:
    """Verify the @bruin.config annotation reaches the driver."""

    @pytest.fixture(autouse=True)
    def _setup(self, duckdb_env):
        pass

    def test_annotation_does_not_break_query(self, monkeypatch):
        monkeypatch.setenv("BRUIN_ASSET", "my_asset")
        monkeypatch.setenv("BRUIN_PIPELINE", "my_pipeline")

        result = query("SELECT 1 AS x", "test_duck")

        assert isinstance(result, pd.DataFrame)
        assert result["x"].iloc[0] == 1
