import json
from unittest.mock import MagicMock, patch

import pytest

from bruin import get_connection
from bruin._connection import Connection, GCPConnection
from bruin.exceptions import (
    ConnectionNotFoundError,
    ConnectionParseError,
    ConnectionTypeError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bq_env(monkeypatch, bq_connection_json):
    """Set up env vars for a BigQuery connection."""
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_bigquery": "google_cloud_platform"}),
    )
    monkeypatch.setenv("my_bigquery", json.dumps(bq_connection_json))


@pytest.fixture
def snowflake_env(monkeypatch, snowflake_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_sf": "snowflake"}),
    )
    monkeypatch.setenv("my_sf", json.dumps(snowflake_connection_json))


@pytest.fixture
def postgres_env(monkeypatch, postgres_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_pg": "postgres"}),
    )
    monkeypatch.setenv("my_pg", json.dumps(postgres_connection_json))


@pytest.fixture
def generic_env(monkeypatch):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"slack_webhook": "generic"}),
    )
    monkeypatch.setenv("slack_webhook", "https://hooks.slack.com/services/T00/B00/xxx")


@pytest.fixture
def multi_env(monkeypatch, bq_connection_json, snowflake_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({
            "my_bigquery": "google_cloud_platform",
            "my_sf": "snowflake",
            "slack_webhook": "generic",
        }),
    )
    monkeypatch.setenv("my_bigquery", json.dumps(bq_connection_json))
    monkeypatch.setenv("my_sf", json.dumps(snowflake_connection_json))
    monkeypatch.setenv("slack_webhook", "https://hooks.slack.com/services/T00/B00/xxx")


# ---------------------------------------------------------------------------
# get_connection() — happy paths
# ---------------------------------------------------------------------------

class TestGetConnection:
    def test_returns_gcp_connection_for_bigquery(self, bq_env):
        conn = get_connection("my_bigquery")
        assert isinstance(conn, GCPConnection)
        assert conn.type == "google_cloud_platform"
        assert conn.name == "my_bigquery"

    def test_returns_connection_for_snowflake(self, snowflake_env):
        conn = get_connection("my_sf")
        assert isinstance(conn, Connection)
        assert not isinstance(conn, GCPConnection)
        assert conn.type == "snowflake"

    def test_returns_connection_for_postgres(self, postgres_env):
        conn = get_connection("my_pg")
        assert conn.type == "postgres"

    def test_generic_connection_raw_is_string(self, generic_env):
        conn = get_connection("slack_webhook")
        assert conn.type == "generic"
        assert isinstance(conn.raw, str)
        assert conn.raw.startswith("https://")

    def test_multiple_connections(self, multi_env):
        bq = get_connection("my_bigquery")
        sf = get_connection("my_sf")
        sl = get_connection("slack_webhook")
        assert isinstance(bq, GCPConnection)
        assert sf.type == "snowflake"
        assert sl.type == "generic"


# ---------------------------------------------------------------------------
# get_connection() — error paths
# ---------------------------------------------------------------------------

class TestGetConnectionErrors:
    def test_no_connection_types_env(self, monkeypatch):
        monkeypatch.delenv("BRUIN_CONNECTION_TYPES", raising=False)
        with pytest.raises(ConnectionNotFoundError, match="BRUIN_CONNECTION_TYPES"):
            get_connection("anything")

    def test_invalid_connection_types_json(self, monkeypatch):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", "not json")
        with pytest.raises(ConnectionParseError, match="Failed to parse BRUIN_CONNECTION_TYPES"):
            get_connection("anything")

    def test_connection_name_not_in_map(self, monkeypatch):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"other": "postgres"}))
        with pytest.raises(ConnectionNotFoundError, match="not found"):
            get_connection("missing")

    def test_connection_env_var_missing(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_pg": "postgres"}),
        )
        monkeypatch.delenv("my_pg", raising=False)
        with pytest.raises(ConnectionNotFoundError, match="env var is not set"):
            get_connection("my_pg")

    def test_invalid_connection_json(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_pg": "postgres"}),
        )
        monkeypatch.setenv("my_pg", "not-json")
        with pytest.raises(ConnectionParseError, match="Failed to parse connection JSON"):
            get_connection("my_pg")


# ---------------------------------------------------------------------------
# Connection.client — lazy init
# ---------------------------------------------------------------------------

class TestConnectionClient:
    def test_generic_raises_connection_type_error(self, generic_env):
        conn = get_connection("slack_webhook")
        with pytest.raises(ConnectionTypeError, match="generic connection"):
            _ = conn.client

    @patch("bruin._connection._create_snowflake")
    def test_snowflake_lazy_init(self, mock_create, snowflake_env):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_sf")
        # Client not created yet
        mock_create.assert_not_called()

        # First access creates client
        assert conn.client is mock_client
        mock_create.assert_called_once()

        # Second access reuses
        assert conn.client is mock_client
        mock_create.assert_called_once()

    @patch("bruin._connection._create_postgres")
    def test_postgres_lazy_init(self, mock_create, postgres_env):
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        conn = get_connection("my_pg")
        assert conn.client is mock_client


# ---------------------------------------------------------------------------
# Snowflake key-pair auth
# ---------------------------------------------------------------------------

class TestSnowflakeKeyPairAuth:
    def test_keypair_passes_private_key_bytes(self, monkeypatch, snowflake_keypair_connection_json):
        """When private_key PEM is set, DER bytes are passed instead of password."""
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_sf": "snowflake"}),
        )
        monkeypatch.setenv("my_sf", json.dumps(snowflake_keypair_connection_json))

        mock_key = MagicMock()
        mock_key.private_bytes.return_value = b"der-bytes"

        mock_connect = MagicMock()

        conn = get_connection("my_sf")
        with patch("snowflake.connector.connect", mock_connect), \
             patch("cryptography.hazmat.primitives.serialization.load_pem_private_key",
                   return_value=mock_key):
            _ = conn.client

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["private_key"] == b"der-bytes"
        assert "password" not in call_kwargs

    def test_password_auth_when_no_private_key(self, monkeypatch, snowflake_connection_json):
        """When private_key is absent/empty, password auth is used."""
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_sf": "snowflake"}),
        )
        monkeypatch.setenv("my_sf", json.dumps(snowflake_connection_json))

        mock_connect = MagicMock()
        conn = get_connection("my_sf")
        with patch("snowflake.connector.connect", mock_connect):
            _ = conn.client

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["password"] == "s3cret"
        assert "private_key" not in call_kwargs


# ---------------------------------------------------------------------------
# GCPConnection
# ---------------------------------------------------------------------------

class TestGCPConnection:
    def test_bigquery_creates_client_with_credentials(self, bq_env, bq_connection_json):
        import sys

        mock_client = MagicMock()
        mock_bq_module = MagicMock()
        mock_bq_module.Client.return_value = mock_client

        mock_sa_module = MagicMock()
        mock_creds = MagicMock()
        mock_sa_module.Credentials.from_service_account_info.return_value = mock_creds

        mock_google = MagicMock()
        mock_google.cloud.bigquery = mock_bq_module
        mock_google.oauth2.service_account = mock_sa_module

        conn = get_connection("my_bigquery")
        with patch.dict(sys.modules, {
            "google": mock_google,
            "google.cloud": mock_google.cloud,
            "google.cloud.bigquery": mock_bq_module,
            "google.oauth2": mock_google.oauth2,
            "google.oauth2.service_account": mock_sa_module,
        }):
            result = conn.bigquery()

        mock_sa_module.Credentials.from_service_account_info.assert_called_once()
        mock_bq_module.Client.assert_called_once_with(
            credentials=mock_creds,
            project=bq_connection_json["project_id"],
        )
        assert result is mock_client

    def test_client_is_alias_for_bigquery(self, bq_env, bq_connection_json):
        conn = get_connection("my_bigquery")
        with patch.object(conn, "bigquery", return_value=MagicMock()) as mock_bq:
            result = conn.client
            mock_bq.assert_called_once()
            assert result is mock_bq.return_value

    def test_credentials_import_error(self, bq_env):
        conn = get_connection("my_bigquery")
        with patch.dict("sys.modules", {"google.oauth2": None, "google.oauth2.service_account": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[bigquery\\]"):
                _ = conn.credentials

    def test_bigquery_import_error(self, bq_env):
        conn = get_connection("my_bigquery")
        with patch.dict("sys.modules", {"google.cloud": None, "google.cloud.bigquery": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[bigquery\\]"):
                conn.bigquery()

    def test_sheets_import_error(self, bq_env):
        conn = get_connection("my_bigquery")
        with patch.dict("sys.modules", {"pygsheets": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[sheets\\]"):
                conn.sheets()

    def test_storage_import_error(self, bq_env):
        conn = get_connection("my_bigquery")
        with patch.dict("sys.modules", {"google.cloud": None, "google.cloud.storage": None}):
            with pytest.raises(ImportError, match="google-cloud-storage"):
                conn.storage()

    def test_raw_contains_connection_fields(self, bq_env, bq_connection_json):
        conn = get_connection("my_bigquery")
        assert conn.raw["project_id"] == bq_connection_json["project_id"]
        assert "service_account_json" in conn.raw

    def test_adc_when_flag_is_true(self, monkeypatch):
        """use_application_default_credentials=true should use google.auth.default()."""
        adc_payload = {
            "project_id": "my-project",
            "service_account_json": "",
            "use_application_default_credentials": "true",
        }
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_gcp": "google_cloud_platform"}),
        )
        monkeypatch.setenv("my_gcp", json.dumps(adc_payload))

        mock_creds = MagicMock()
        conn = get_connection("my_gcp")
        with patch("google.auth.default", return_value=(mock_creds, "my-project")):
            assert conn.credentials is mock_creds

    def test_adc_fallback_when_no_sa_json(self, monkeypatch):
        """When service_account_json is empty and ADC flag is not set, fall back to ADC."""
        payload = {
            "project_id": "my-project",
            "service_account_json": "",
            "use_application_default_credentials": "false",
        }
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_gcp": "google_cloud_platform"}),
        )
        monkeypatch.setenv("my_gcp", json.dumps(payload))

        mock_creds = MagicMock()
        conn = get_connection("my_gcp")
        with patch("google.auth.default", return_value=(mock_creds, "my-project")):
            assert conn.credentials is mock_creds

    def test_adc_import_error(self, monkeypatch):
        adc_payload = {
            "project_id": "my-project",
            "service_account_json": "",
            "use_application_default_credentials": "true",
        }
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_gcp": "google_cloud_platform"}),
        )
        monkeypatch.setenv("my_gcp", json.dumps(adc_payload))

        conn = get_connection("my_gcp")
        with patch.dict("sys.modules", {"google.auth": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[bigquery\\]"):
                _ = conn.credentials


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestConnectionContextManager:
    @patch("bruin._connection._create_postgres")
    def test_context_manager_closes_client(self, mock_create, postgres_env):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        with get_connection("my_pg") as conn:
            _ = conn.client  # trigger lazy init

        mock_client.close.assert_called_once()

    @patch("bruin._connection._create_postgres")
    def test_context_manager_without_client_access(self, mock_create, postgres_env):
        """Context manager should not fail if client was never accessed."""
        with get_connection("my_pg") as conn:
            pass  # never access .client

        mock_create.assert_not_called()

    @patch("bruin._connection._create_snowflake")
    def test_close_resets_client(self, mock_create, snowflake_env):
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_sf")
        _ = conn.client
        conn.close()
        mock_client.close.assert_called_once()

        # Client should be re-created on next access
        mock_client2 = MagicMock()
        mock_create.return_value = mock_client2
        assert conn.client is mock_client2

    @patch("bruin._connection._create_postgres")
    def test_context_manager_closes_on_exception(self, mock_create, postgres_env):
        """close() must be called even when the with-block raises."""
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        with pytest.raises(RuntimeError, match="boom"):
            with get_connection("my_pg") as conn:
                _ = conn.client
                raise RuntimeError("boom")

        mock_client.close.assert_called_once()

    def test_gcp_close_closes_bigquery_client(self, bq_env):
        conn = get_connection("my_bigquery")
        mock_bq_client = MagicMock()
        conn._bigquery_client = mock_bq_client
        conn._credentials = MagicMock()

        conn.close()

        mock_bq_client.close.assert_called_once()
        assert conn._bigquery_client is None
        assert conn._credentials is None

    def test_gcp_context_manager_closes_bigquery_client(self, bq_env):
        mock_bq_client = MagicMock()

        with get_connection("my_bigquery") as conn:
            conn._bigquery_client = mock_bq_client
            conn._credentials = MagicMock()

        mock_bq_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# New connection types
# ---------------------------------------------------------------------------

class TestNewConnectionTypes:
    def test_databricks_connection(self, monkeypatch, databricks_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_db": "databricks"}),
        )
        monkeypatch.setenv("my_db", json.dumps(databricks_connection_json))
        conn = get_connection("my_db")
        assert conn.type == "databricks"
        assert conn.raw["host"] == "dbc-abc123.cloud.databricks.com"

    def test_clickhouse_connection(self, monkeypatch, clickhouse_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_ch": "clickhouse"}),
        )
        monkeypatch.setenv("my_ch", json.dumps(clickhouse_connection_json))
        conn = get_connection("my_ch")
        assert conn.type == "clickhouse"

    def test_athena_connection(self, monkeypatch, athena_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_athena": "athena"}),
        )
        monkeypatch.setenv("my_athena", json.dumps(athena_connection_json))
        conn = get_connection("my_athena")
        assert conn.type == "athena"

    def test_trino_connection(self, monkeypatch, trino_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_trino": "trino"}),
        )
        monkeypatch.setenv("my_trino", json.dumps(trino_connection_json))
        conn = get_connection("my_trino")
        assert conn.type == "trino"

    def test_sqlite_connection(self, monkeypatch, sqlite_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_sqlite": "sqlite"}),
        )
        monkeypatch.setenv("my_sqlite", json.dumps(sqlite_connection_json))
        conn = get_connection("my_sqlite")
        assert conn.type == "sqlite"

    def test_motherduck_connection(self, monkeypatch, motherduck_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_md": "motherduck"}),
        )
        monkeypatch.setenv("my_md", json.dumps(motherduck_connection_json))
        conn = get_connection("my_md")
        assert conn.type == "motherduck"

    def test_synapse_connection(self, monkeypatch, mssql_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_syn": "synapse"}),
        )
        monkeypatch.setenv("my_syn", json.dumps(mssql_connection_json))
        conn = get_connection("my_syn")
        assert conn.type == "synapse"

    def test_fabric_connection(self, monkeypatch, fabric_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_fabric": "fabric"}),
        )
        monkeypatch.setenv("my_fabric", json.dumps(fabric_connection_json))
        conn = get_connection("my_fabric")
        assert conn.type == "fabric"
        assert conn.raw["host"] == "fabric.example.com"

    def test_oracle_connection(self, monkeypatch, oracle_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_oracle": "oracle"}),
        )
        monkeypatch.setenv("my_oracle", json.dumps(oracle_connection_json))
        conn = get_connection("my_oracle")
        assert conn.type == "oracle"
        assert conn.raw["service_name"] == "ORCL"

    def test_db2_connection(self, monkeypatch, db2_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_db2": "db2"}),
        )
        monkeypatch.setenv("my_db2", json.dumps(db2_connection_json))
        conn = get_connection("my_db2")
        assert conn.type == "db2"

    def test_hana_connection(self, monkeypatch, hana_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_hana": "hana"}),
        )
        monkeypatch.setenv("my_hana", json.dumps(hana_connection_json))
        conn = get_connection("my_hana")
        assert conn.type == "hana"

    def test_spanner_connection(self, monkeypatch, spanner_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_spanner": "spanner"}),
        )
        monkeypatch.setenv("my_spanner", json.dumps(spanner_connection_json))
        conn = get_connection("my_spanner")
        assert conn.type == "spanner"

    def test_vertica_connection(self, monkeypatch, vertica_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_vertica": "vertica"}),
        )
        monkeypatch.setenv("my_vertica", json.dumps(vertica_connection_json))
        conn = get_connection("my_vertica")
        assert conn.type == "vertica"
        assert conn.raw["host"] == "vertica.example.com"


# ---------------------------------------------------------------------------
# Import error messages for new types
# ---------------------------------------------------------------------------

class TestNewConnectionImportErrors:
    @patch.dict("sys.modules", {"databricks": None, "databricks.sql": None})
    def test_databricks_import_error(self, monkeypatch, databricks_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_db": "databricks"}),
        )
        monkeypatch.setenv("my_db", json.dumps(databricks_connection_json))
        conn = get_connection("my_db")
        with pytest.raises(ImportError, match="bruin-sdk\\[databricks\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"clickhouse_connect": None})
    def test_clickhouse_import_error(self, monkeypatch, clickhouse_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_ch": "clickhouse"}),
        )
        monkeypatch.setenv("my_ch", json.dumps(clickhouse_connection_json))
        conn = get_connection("my_ch")
        with pytest.raises(ImportError, match="bruin-sdk\\[clickhouse\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"pyathena": None})
    def test_athena_import_error(self, monkeypatch, athena_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_athena": "athena"}),
        )
        monkeypatch.setenv("my_athena", json.dumps(athena_connection_json))
        conn = get_connection("my_athena")
        with pytest.raises(ImportError, match="bruin-sdk\\[athena\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"trino": None, "trino.dbapi": None})
    def test_trino_import_error(self, monkeypatch, trino_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_trino": "trino"}),
        )
        monkeypatch.setenv("my_trino", json.dumps(trino_connection_json))
        conn = get_connection("my_trino")
        with pytest.raises(ImportError, match="bruin-sdk\\[trino\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"oracledb": None})
    def test_oracle_import_error(self, monkeypatch, oracle_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_oracle": "oracle"}),
        )
        monkeypatch.setenv("my_oracle", json.dumps(oracle_connection_json))
        conn = get_connection("my_oracle")
        with pytest.raises(ImportError, match="bruin-sdk\\[oracle\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"ibm_db_dbi": None})
    def test_db2_import_error(self, monkeypatch, db2_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_db2": "db2"}),
        )
        monkeypatch.setenv("my_db2", json.dumps(db2_connection_json))
        conn = get_connection("my_db2")
        with pytest.raises(ImportError, match="bruin-sdk\\[db2\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"hdbcli": None, "hdbcli.dbapi": None})
    def test_hana_import_error(self, monkeypatch, hana_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_hana": "hana"}),
        )
        monkeypatch.setenv("my_hana", json.dumps(hana_connection_json))
        conn = get_connection("my_hana")
        with pytest.raises(ImportError, match="bruin-sdk\\[hana\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"vertica_python": None})
    def test_vertica_import_error(self, monkeypatch, vertica_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_vertica": "vertica"}),
        )
        monkeypatch.setenv("my_vertica", json.dumps(vertica_connection_json))
        conn = get_connection("my_vertica")
        with pytest.raises(ImportError, match="bruin-sdk\\[vertica\\]"):
            _ = conn.client

    @patch.dict("sys.modules", {"google.cloud.spanner_dbapi": None, "google": None, "google.cloud": None})
    def test_spanner_import_error(self, monkeypatch, spanner_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_spanner": "spanner"}),
        )
        monkeypatch.setenv("my_spanner", json.dumps(spanner_connection_json))
        conn = get_connection("my_spanner")
        with pytest.raises(ImportError, match="bruin-sdk\\[spanner\\]"):
            _ = conn.client


# ---------------------------------------------------------------------------
# Lazy client creation for new types
# ---------------------------------------------------------------------------

class TestNewConnectionLazyInit:
    @patch("bruin._connection._create_databricks")
    def test_databricks_lazy_init(self, mock_create, monkeypatch, databricks_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_db": "databricks"}))
        monkeypatch.setenv("my_db", json.dumps(databricks_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_db")
        mock_create.assert_not_called()
        assert conn.client is mock_client
        mock_create.assert_called_once()

    @patch("bruin._connection._create_clickhouse")
    def test_clickhouse_lazy_init(self, mock_create, monkeypatch, clickhouse_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_ch": "clickhouse"}))
        monkeypatch.setenv("my_ch", json.dumps(clickhouse_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_ch")
        assert conn.client is mock_client

    @patch("bruin._connection._create_oracle")
    def test_oracle_lazy_init(self, mock_create, monkeypatch, oracle_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_oracle": "oracle"}))
        monkeypatch.setenv("my_oracle", json.dumps(oracle_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_oracle")
        mock_create.assert_not_called()
        assert conn.client is mock_client
        mock_create.assert_called_once()

    @patch("bruin._connection._create_db2")
    def test_db2_lazy_init(self, mock_create, monkeypatch, db2_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_db2": "db2"}))
        monkeypatch.setenv("my_db2", json.dumps(db2_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_db2")
        assert conn.client is mock_client

    @patch("bruin._connection._create_hana")
    def test_hana_lazy_init(self, mock_create, monkeypatch, hana_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_hana": "hana"}))
        monkeypatch.setenv("my_hana", json.dumps(hana_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_hana")
        assert conn.client is mock_client

    @patch("bruin._connection._create_spanner")
    def test_spanner_lazy_init(self, mock_create, monkeypatch, spanner_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_spanner": "spanner"}))
        monkeypatch.setenv("my_spanner", json.dumps(spanner_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_spanner")
        assert conn.client is mock_client

    @patch("bruin._connection._create_vertica")
    def test_vertica_lazy_init(self, mock_create, monkeypatch, vertica_connection_json):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_vertica": "vertica"}))
        monkeypatch.setenv("my_vertica", json.dumps(vertica_connection_json))
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        conn = get_connection("my_vertica")
        mock_create.assert_not_called()
        assert conn.client is mock_client
        mock_create.assert_called_once()

    def test_sqlite_creates_real_connection(self, monkeypatch, sqlite_connection_json):
        """SQLite uses stdlib — no mocking needed."""
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"my_sqlite": "sqlite"}))
        monkeypatch.setenv("my_sqlite", json.dumps(sqlite_connection_json))

        conn = get_connection("my_sqlite")
        client = conn.client
        # Verify it's a real sqlite3 connection
        cur = client.execute("SELECT 1")
        assert cur.fetchone() == (1,)
        conn.close()


# ---------------------------------------------------------------------------
# Unsupported type
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Factory-level tests (verify actual driver kwargs)
# ---------------------------------------------------------------------------

class TestFactoryArgs:
    def test_oracle_service_name(self, oracle_connection_json):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"oracledb": mock_mod}):
            from bruin._connection import _create_oracle
            _create_oracle(oracle_connection_json)
        mock_mod.connect.assert_called_once_with(
            user="system",
            password="s3cret",
            host="oracle.example.com",
            port=1521,
            service_name="ORCL",
        )

    def test_oracle_sid(self, oracle_sid_connection_json):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"oracledb": mock_mod}):
            from bruin._connection import _create_oracle
            _create_oracle(oracle_sid_connection_json)
        mock_mod.connect.assert_called_once_with(
            user="system",
            password="s3cret",
            host="oracle.example.com",
            port=1521,
            sid="XE",
        )

    def test_db2_connection_string(self, db2_connection_json):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"ibm_db_dbi": mock_mod}):
            from bruin._connection import _create_db2
            _create_db2(db2_connection_json)
        conn_str = mock_mod.connect.call_args[0][0]
        assert "DATABASE=SAMPLE;" in conn_str
        assert "HOSTNAME=db2.example.com;" in conn_str
        assert "PORT=50000;" in conn_str
        assert "UID=db2admin;" in conn_str
        assert "PWD=s3cret;" in conn_str

    def test_hana_kwargs(self, hana_connection_json):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"hdbcli": mock_mod, "hdbcli.dbapi": mock_mod.dbapi}):
            from bruin._connection import _create_hana
            _create_hana(hana_connection_json)
        mock_mod.dbapi.connect.assert_called_once_with(
            address="hana.example.com",
            port=30015,
            user="SYSTEM",
            password="s3cret",
            databaseName="HDB",
        )

    def test_vertica_kwargs(self, vertica_connection_json):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"vertica_python": mock_mod}):
            from bruin._connection import _create_vertica
            _create_vertica(vertica_connection_json)
        mock_mod.connect.assert_called_once_with(
            host="vertica.example.com",
            port=5433,
            user="dbadmin",
            password="s3cret",
            database="analytics",
        )

    def test_spanner_kwargs(self, spanner_connection_json):
        mock_connect = MagicMock()
        mock_mod = MagicMock()
        mock_mod.connect = mock_connect
        with patch.dict("sys.modules", {
            "google": MagicMock(),
            "google.cloud": MagicMock(),
            "google.cloud.spanner_dbapi": mock_mod,
        }):
            from bruin._connection import _create_spanner
            _create_spanner(spanner_connection_json)
        mock_connect.assert_called_once_with(
            instance_id="my-instance",
            database_id="my-db",
            project="my-gcp-project",
        )

    def test_redshift_uses_port_5439(self):
        mock_mod = MagicMock()
        with patch.dict("sys.modules", {"psycopg2": mock_mod}):
            from bruin._connection import _create_redshift
            _create_redshift({"host": "rs.example.com", "username": "admin", "password": "pw"})
        _, kwargs = mock_mod.connect.call_args
        assert kwargs["port"] == 5439
        assert kwargs["sslmode"] == "allow"


class TestRepr:
    def test_connection_repr(self):
        conn = Connection("my_pg", "postgres", {"host": "localhost"})
        assert repr(conn) == "Connection(name='my_pg', type='postgres')"

    def test_gcp_connection_repr(self):
        conn = GCPConnection("my_bq", {"project_id": "test"})
        assert repr(conn) == "Connection(name='my_bq', type='google_cloud_platform')"


class TestUnsupportedType:
    def test_raises_connection_type_error(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_conn": "unknown_db"}),
        )
        monkeypatch.setenv("my_conn", json.dumps({"host": "localhost"}))
        conn = get_connection("my_conn")
        with pytest.raises(ConnectionTypeError, match="Unsupported connection type"):
            _ = conn.client
