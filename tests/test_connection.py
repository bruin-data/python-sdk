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


# ---------------------------------------------------------------------------
# Unsupported type
# ---------------------------------------------------------------------------

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
