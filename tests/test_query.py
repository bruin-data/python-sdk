import json
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from bruin import query
from bruin._connection import Connection, GCPConnection
from bruin.exceptions import ConnectionTypeError, QueryError


@pytest.fixture
def _setup_bq(monkeypatch, bq_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_bq": "google_cloud_platform"}),
    )
    monkeypatch.setenv("my_bq", json.dumps(bq_connection_json))


@pytest.fixture
def _setup_snowflake(monkeypatch, snowflake_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_sf": "snowflake"}),
    )
    monkeypatch.setenv("my_sf", json.dumps(snowflake_connection_json))


@pytest.fixture
def _setup_postgres(monkeypatch, postgres_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_pg": "postgres"}),
    )
    monkeypatch.setenv("my_pg", json.dumps(postgres_connection_json))


@pytest.fixture
def _setup_duckdb(monkeypatch):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_duck": "duckdb"}),
    )
    monkeypatch.setenv("my_duck", json.dumps({"path": ":memory:"}))


@pytest.fixture
def _setup_generic(monkeypatch):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"slack": "generic"}),
    )
    monkeypatch.setenv("slack", "https://hooks.slack.com/xxx")


@pytest.fixture
def sample_df():
    return pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})


def _assert_annotated(call_args, original_sql):
    """Assert that the SQL passed to the mock contains @bruin.config and the original SQL."""
    sql_arg = call_args[0][0]
    assert "-- @bruin.config:" in sql_arg
    assert original_sql in sql_arg


# ---------------------------------------------------------------------------
# BigQuery
# ---------------------------------------------------------------------------

class TestQueryBigQuery:
    @pytest.mark.usefixtures("_setup_bq")
    def test_select_returns_dataframe(self, sample_df):
        mock_client = MagicMock()
        mock_client.query.return_value.to_dataframe.return_value = sample_df

        with patch("bruin._connection.GCPConnection.bigquery", return_value=mock_client):
            result = query("SELECT 1", "my_bq")

        _assert_annotated(mock_client.query.call_args, "SELECT 1")
        mock_client.query.return_value.to_dataframe.assert_called_once()
        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_bq")
    def test_ddl_returns_none(self):
        mock_client = MagicMock()
        mock_job = MagicMock()
        mock_client.query.return_value = mock_job

        with patch("bruin._connection.GCPConnection.bigquery", return_value=mock_client):
            result = query("CREATE TABLE foo (id INT)", "my_bq")

        assert result is None
        mock_job.result.assert_called_once()
        mock_job.to_dataframe.assert_not_called()


# ---------------------------------------------------------------------------
# Snowflake
# ---------------------------------------------------------------------------

class TestQuerySnowflake:
    @pytest.mark.usefixtures("_setup_snowflake")
    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = mock_cursor
        mock_cursor.fetch_pandas_all.return_value = sample_df

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_snowflake", return_value=mock_client):
            result = query("SELECT 1", "my_sf")

        _assert_annotated(mock_cursor.execute.call_args, "SELECT 1")
        mock_cursor.fetch_pandas_all.assert_called_once()
        mock_cursor.close.assert_called_once()
        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_snowflake")
    def test_ddl_returns_none(self):
        mock_cursor = MagicMock()
        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_snowflake", return_value=mock_client):
            result = query("INSERT INTO foo VALUES (1)", "my_sf")

        assert result is None
        mock_cursor.fetch_pandas_all.assert_not_called()


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------

class TestQueryPostgres:
    @pytest.mark.usefixtures("_setup_postgres")
    def test_select_returns_dataframe(self, sample_df):
        mock_client = MagicMock()

        with patch("bruin._connection._create_postgres", return_value=mock_client):
            with patch("bruin._query.pd.read_sql", return_value=sample_df) as mock_read:
                result = query("SELECT 1", "my_pg")

        _assert_annotated(mock_read.call_args, "SELECT 1")
        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_postgres")
    def test_ddl_returns_none(self):
        mock_cursor = MagicMock()
        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_postgres", return_value=mock_client):
            result = query("DELETE FROM foo WHERE id = 1", "my_pg")

        assert result is None
        mock_cursor.execute.assert_called_once()
        mock_client.commit.assert_called_once()


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------

class TestQueryDuckDB:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_select_returns_dataframe(self, sample_df):
        mock_client = MagicMock()
        mock_client.execute.return_value.fetchdf.return_value = sample_df

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            result = query("SELECT 1", "my_duck")

        _assert_annotated(mock_client.execute.call_args, "SELECT 1")
        mock_client.execute.return_value.fetchdf.assert_called_once()
        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_duckdb")
    def test_ddl_returns_none(self):
        mock_client = MagicMock()

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            result = query("DROP TABLE foo", "my_duck")

        assert result is None


# ---------------------------------------------------------------------------
# Default connection from BRUIN_CONNECTION
# ---------------------------------------------------------------------------

class TestDefaultConnection:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_uses_bruin_connection_env_when_no_connection_arg(self, monkeypatch, sample_df):
        monkeypatch.setenv("BRUIN_CONNECTION", "my_duck")
        mock_client = MagicMock()
        mock_client.execute.return_value.fetchdf.return_value = sample_df

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            result = query("SELECT 1")

        pd.testing.assert_frame_equal(result, sample_df)

    def test_raises_when_no_connection_and_no_default(self, monkeypatch):
        monkeypatch.delenv("BRUIN_CONNECTION", raising=False)
        with pytest.raises(ConnectionTypeError, match="No connection specified"):
            query("SELECT 1")


# ---------------------------------------------------------------------------
# @bruin.config annotation
# ---------------------------------------------------------------------------

class TestAnnotation:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_annotation_includes_asset_and_pipeline(self, monkeypatch, sample_df):
        monkeypatch.setenv("BRUIN_ASSET", "test_asset")
        monkeypatch.setenv("BRUIN_PIPELINE", "test_pipeline")

        mock_client = MagicMock()
        mock_client.execute.return_value.fetchdf.return_value = sample_df

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            query("SELECT 1", "my_duck")

        sql_sent = mock_client.execute.call_args[0][0]
        assert "-- @bruin.config:" in sql_sent
        assert '"asset":"test_asset"' in sql_sent
        assert '"pipeline":"test_pipeline"' in sql_sent
        assert '"type":"python_query"' in sql_sent


# ---------------------------------------------------------------------------
# DDL/DML detection
# ---------------------------------------------------------------------------

class TestReturnsData:
    @pytest.mark.parametrize("sql", [
        "SELECT 1",
        "  select * from foo",
        "WITH cte AS (SELECT 1) SELECT * FROM cte",
        "SHOW TABLES",
        "DESCRIBE foo",
        "DESC foo",
        "EXPLAIN SELECT 1",
        "TABLE foo",
        "VALUES (1, 2)",
    ])
    def test_data_returning(self, sql):
        from bruin._query import _returns_data
        assert _returns_data(sql) is True

    @pytest.mark.parametrize("sql", [
        "CREATE TABLE foo (id INT)",
        "INSERT INTO foo VALUES (1)",
        "UPDATE foo SET x = 1",
        "DELETE FROM foo WHERE id = 1",
        "DROP TABLE foo",
        "ALTER TABLE foo ADD COLUMN x INT",
        "TRUNCATE TABLE foo",
        "GRANT SELECT ON foo TO bar",
    ])
    def test_non_data_returning(self, sql):
        from bruin._query import _returns_data
        assert _returns_data(sql) is False

    def test_with_leading_comment(self):
        from bruin._query import _returns_data
        sql = "-- @bruin.config: {}\nSELECT 1"
        assert _returns_data(sql) is True

    def test_ddl_with_leading_comment(self):
        from bruin._query import _returns_data
        sql = "-- @bruin.config: {}\nCREATE TABLE foo (id INT)"
        assert _returns_data(sql) is False


# ---------------------------------------------------------------------------
# Connection.query()
# ---------------------------------------------------------------------------

class TestConnectionQuery:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_conn_query_returns_dataframe(self, sample_df):
        from bruin import get_connection

        mock_client = MagicMock()
        mock_client.execute.return_value.fetchdf.return_value = sample_df

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            conn = get_connection("my_duck")
            result = conn.query("SELECT 1")

        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_generic")
    def test_generic_conn_query_raises(self):
        from bruin import get_connection

        conn = get_connection("slack")
        with pytest.raises(ConnectionTypeError, match="generic connection"):
            conn.query("SELECT 1")

    @pytest.mark.usefixtures("_setup_duckdb")
    def test_conn_query_ddl_returns_none(self):
        from bruin import get_connection

        mock_client = MagicMock()

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            conn = get_connection("my_duck")
            result = conn.query("CREATE TABLE foo (id INT)")

        assert result is None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestQueryErrors:
    @pytest.mark.usefixtures("_setup_generic")
    def test_generic_connection_raises(self):
        with pytest.raises(ConnectionTypeError, match="generic connection"):
            query("SELECT 1", "slack")

    @pytest.mark.usefixtures("_setup_snowflake")
    def test_client_exception_wraps_in_query_error(self):
        mock_client = MagicMock()
        mock_client.cursor.side_effect = RuntimeError("connection refused")

        with patch("bruin._connection._create_snowflake", return_value=mock_client):
            with pytest.raises(QueryError, match="connection refused"):
                query("SELECT 1", "my_sf")
