import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bruin import query
from bruin.exceptions import ConnectionNotFoundError, ConnectionTypeError, QueryError


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
        mock_rows = MagicMock()
        mock_rows.schema = [MagicMock()]
        mock_rows.to_dataframe.return_value = sample_df

        mock_client = MagicMock()
        mock_client.query.return_value.result.return_value = mock_rows

        with patch("bruin._connection.GCPConnection.bigquery", return_value=mock_client):
            result = query("SELECT 1", "my_bq")

        _assert_annotated(mock_client.query.call_args, "SELECT 1")
        mock_rows.to_dataframe.assert_called_once()
        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_bq")
    def test_ddl_returns_none(self):
        mock_rows = MagicMock()
        mock_rows.schema = []

        mock_client = MagicMock()
        mock_client.query.return_value.result.return_value = mock_rows

        with patch("bruin._connection.GCPConnection.bigquery", return_value=mock_client):
            result = query("CREATE TABLE foo (id INT)", "my_bq")

        assert result is None
        mock_rows.to_dataframe.assert_not_called()


# ---------------------------------------------------------------------------
# Snowflake
# ---------------------------------------------------------------------------


class TestQuerySnowflake:
    @pytest.mark.usefixtures("_setup_snowflake")
    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
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
        mock_cursor.description = None

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
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_postgres", return_value=mock_client):
            result = query("SELECT 1", "my_pg")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]
        mock_cursor.close.assert_called_once()

    @pytest.mark.usefixtures("_setup_postgres")
    def test_ddl_returns_none(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

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
        mock_result = MagicMock()
        mock_result.description = [("id",), ("name",)]
        mock_result.fetchdf.return_value = sample_df

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            result = query("SELECT 1", "my_duck")

        _assert_annotated(mock_client.execute.call_args, "SELECT 1")
        mock_result.fetchdf.assert_called_once()
        pd.testing.assert_frame_equal(result, sample_df)

    @pytest.mark.usefixtures("_setup_duckdb")
    def test_ddl_returns_none(self):
        mock_result = MagicMock()
        mock_result.description = None

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            result = query("DROP TABLE foo", "my_duck")

        assert result is None


# ---------------------------------------------------------------------------
# Databricks
# ---------------------------------------------------------------------------


class TestQueryDatabricks:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, databricks_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_db": "databricks"}),
        )
        monkeypatch.setenv("my_db", json.dumps(databricks_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_databricks", return_value=mock_client):
            result = query("SELECT * FROM users", "my_db")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]
        mock_cursor.close.assert_called_once()

    def test_ddl_returns_none(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_databricks", return_value=mock_client):
            result = query("CREATE TABLE foo (id INT)", "my_db")

        assert result is None
        mock_cursor.close.assert_called_once()


# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------


class TestQueryClickHouse:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, clickhouse_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_ch": "clickhouse"}),
        )
        monkeypatch.setenv("my_ch", json.dumps(clickhouse_connection_json))

    def test_select_returns_dataframe(self):
        mock_result = MagicMock()
        mock_result.result_rows = [(1, "a"), (2, "b")]
        mock_result.column_names = ["id", "name"]

        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("bruin._connection._create_clickhouse", return_value=mock_client):
            result = query("SELECT * FROM users", "my_ch")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_returns_none(self):
        mock_result = MagicMock()
        mock_result.column_names = []

        mock_client = MagicMock()
        mock_client.query.return_value = mock_result

        with patch("bruin._connection._create_clickhouse", return_value=mock_client):
            result = query("CREATE TABLE foo (id Int32)", "my_ch")

        assert result is None


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


class TestQuerySQLite:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, sqlite_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_sqlite": "sqlite"}),
        )
        monkeypatch.setenv("my_sqlite", json.dumps(sqlite_connection_json))

    def test_select_returns_dataframe(self):
        """SQLite uses a real :memory: connection — no mocking needed."""
        result = query("SELECT 1 AS id, 'hello' AS name", "my_sqlite")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]
        assert len(result) == 1

    def test_ddl_returns_none(self):
        result = query("CREATE TABLE IF NOT EXISTS test_tbl (id INTEGER)", "my_sqlite")
        assert result is None


# ---------------------------------------------------------------------------
# Athena (uses DBAPI cursor path)
# ---------------------------------------------------------------------------


class TestQueryAthena:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, athena_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_athena": "athena"}))
        monkeypatch.setenv("my_athena", json.dumps(athena_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_athena", return_value=mock_client):
            result = query("SELECT 1", "my_athena")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_does_not_commit(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_athena", return_value=mock_client):
            result = query("CREATE TABLE foo (id INT)", "my_athena")

        assert result is None
        mock_client.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Trino (uses DBAPI cursor path, no commit)
# ---------------------------------------------------------------------------


class TestQueryTrino:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, trino_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_trino": "trino"}))
        monkeypatch.setenv("my_trino", json.dumps(trino_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_trino", return_value=mock_client):
            result = query("SELECT 1", "my_trino")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_does_not_commit(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_trino", return_value=mock_client):
            result = query("INSERT INTO foo VALUES (1)", "my_trino")

        assert result is None
        mock_client.commit.assert_not_called()


# ---------------------------------------------------------------------------
# MotherDuck (uses duckdb path)
# ---------------------------------------------------------------------------


class TestQueryMotherDuck:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, motherduck_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_md": "motherduck"}))
        monkeypatch.setenv("my_md", json.dumps(motherduck_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_result = MagicMock()
        mock_result.description = [("id",), ("name",)]
        mock_result.fetchdf.return_value = sample_df

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

        with patch("bruin._connection._create_motherduck", return_value=mock_client):
            result = query("SELECT 1", "my_md")

        pd.testing.assert_frame_equal(result, sample_df)

    def test_ddl_returns_none(self):
        mock_result = MagicMock()
        mock_result.description = None

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

        with patch("bruin._connection._create_motherduck", return_value=mock_client):
            result = query("DROP TABLE foo", "my_md")

        assert result is None


# ---------------------------------------------------------------------------
# MSSQL
# ---------------------------------------------------------------------------


class TestQueryMSSQL:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, mssql_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_mssql": "mssql"}))
        monkeypatch.setenv("my_mssql", json.dumps(mssql_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_mssql", return_value=mock_client):
            result = query("SELECT 1", "my_mssql")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_mssql", return_value=mock_client):
            result = query("DELETE FROM foo WHERE id = 1", "my_mssql")

        assert result is None
        mock_client.commit.assert_called_once()


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------


class TestQueryMySQL:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, mysql_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_mysql": "mysql"}))
        monkeypatch.setenv("my_mysql", json.dumps(mysql_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_mysql", return_value=mock_client):
            result = query("SELECT 1", "my_mysql")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]


# ---------------------------------------------------------------------------
# Synapse (reuses MSSQL path)
# ---------------------------------------------------------------------------


class TestQuerySynapse:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, mssql_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_syn": "synapse"}))
        monkeypatch.setenv("my_syn", json.dumps(mssql_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_mssql", return_value=mock_client):
            result = query("SELECT 1", "my_syn")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]


class TestQueryFabric:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, fabric_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_fabric": "fabric"}))
        monkeypatch.setenv("my_fabric", json.dumps(fabric_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_mssql", return_value=mock_client):
            result = query("SELECT 1", "my_fabric")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_mssql", return_value=mock_client):
            result = query("CREATE TABLE t (id INT)", "my_fabric")

        assert result is None
        mock_client.commit.assert_called_once()


class TestQueryOracle:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, oracle_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_oracle": "oracle"}))
        monkeypatch.setenv("my_oracle", json.dumps(oracle_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_oracle", return_value=mock_client):
            result = query("SELECT 1 FROM dual", "my_oracle")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_oracle", return_value=mock_client):
            result = query("CREATE TABLE t (id NUMBER)", "my_oracle")

        assert result is None
        mock_client.commit.assert_called_once()


class TestQueryDB2:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, db2_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_db2": "db2"}))
        monkeypatch.setenv("my_db2", json.dumps(db2_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_db2", return_value=mock_client):
            result = query("SELECT 1 FROM sysibm.sysdummy1", "my_db2")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_db2", return_value=mock_client):
            result = query("CREATE TABLE t (id INT)", "my_db2")

        assert result is None
        mock_client.commit.assert_called_once()


class TestQueryHANA:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, hana_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_hana": "hana"}))
        monkeypatch.setenv("my_hana", json.dumps(hana_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_hana", return_value=mock_client):
            result = query("SELECT 1 FROM dummy", "my_hana")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_hana", return_value=mock_client):
            result = query("CREATE TABLE t (id INT)", "my_hana")

        assert result is None
        mock_client.commit.assert_called_once()


class TestQueryVertica:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, vertica_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_vertica": "vertica"}))
        monkeypatch.setenv("my_vertica", json.dumps(vertica_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_vertica", return_value=mock_client):
            result = query("SELECT 1", "my_vertica")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_vertica", return_value=mock_client):
            result = query("CREATE TABLE t (id INT)", "my_vertica")

        assert result is None
        mock_client.commit.assert_called_once()


class TestQuerySpanner:
    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, spanner_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_spanner": "spanner"}))
        monkeypatch.setenv("my_spanner", json.dumps(spanner_connection_json))

    def test_select_returns_dataframe(self, sample_df):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "a"), (2, "b")]

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_spanner", return_value=mock_client):
            result = query("SELECT 1", "my_spanner")

        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["id", "name"]

    def test_ddl_commits(self):
        """Spanner DML/DDL needs commit() — autocommit is off by default."""
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_client = MagicMock()
        mock_client.cursor.return_value = mock_cursor

        with patch("bruin._connection._create_spanner", return_value=mock_client):
            result = query("INSERT INTO t (id) VALUES (1)", "my_spanner")

        assert result is None
        mock_client.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Default connection from BRUIN_CONNECTION
# ---------------------------------------------------------------------------


class TestDefaultConnection:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_uses_bruin_connection_env_when_no_connection_arg(self, monkeypatch, sample_df):
        monkeypatch.setenv("BRUIN_CONNECTION", "my_duck")

        mock_result = MagicMock()
        mock_result.description = [("id",), ("name",)]
        mock_result.fetchdf.return_value = sample_df

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            result = query("SELECT 1")

        pd.testing.assert_frame_equal(result, sample_df)

    def test_raises_when_no_connection_and_no_default(self, monkeypatch):
        monkeypatch.delenv("BRUIN_CONNECTION", raising=False)
        with pytest.raises(ConnectionNotFoundError, match="No connection specified"):
            query("SELECT 1")


# ---------------------------------------------------------------------------
# @bruin.config annotation
# ---------------------------------------------------------------------------


class TestAnnotation:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_annotation_includes_asset_and_pipeline(self, monkeypatch, sample_df):
        monkeypatch.setenv("BRUIN_ASSET", "test_asset")
        monkeypatch.setenv("BRUIN_PIPELINE", "test_pipeline")

        mock_result = MagicMock()
        mock_result.description = [("id",), ("name",)]
        mock_result.fetchdf.return_value = sample_df

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

        with patch("bruin._connection._create_duckdb", return_value=mock_client):
            query("SELECT 1", "my_duck")

        sql_sent = mock_client.execute.call_args[0][0]
        assert "-- @bruin.config:" in sql_sent
        assert '"asset":"test_asset"' in sql_sent
        assert '"pipeline":"test_pipeline"' in sql_sent
        assert '"type":"python_query"' in sql_sent


# ---------------------------------------------------------------------------
# Connection.query()
# ---------------------------------------------------------------------------


class TestConnectionQuery:
    @pytest.mark.usefixtures("_setup_duckdb")
    def test_conn_query_returns_dataframe(self, sample_df):
        from bruin import get_connection

        mock_result = MagicMock()
        mock_result.description = [("id",), ("name",)]
        mock_result.fetchdf.return_value = sample_df

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

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

        mock_result = MagicMock()
        mock_result.description = None

        mock_client = MagicMock()
        mock_client.execute.return_value = mock_result

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
