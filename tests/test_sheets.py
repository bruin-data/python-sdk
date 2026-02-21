import json
import sys
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

from bruin import get_connection, read_sheet, write_sheet
from bruin._connection import GCPConnection, GoogleSheetsConnection
from bruin._sheets import _get_sheets_client, _read_sheet_impl, _write_sheet_impl
from bruin.exceptions import (
    ConnectionNotFoundError,
    ConnectionParseError,
    ConnectionTypeError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_google_modules():
    """Create mock google.oauth2.service_account module hierarchy."""
    mock_sa_module = MagicMock()
    mock_creds = MagicMock()
    mock_sa_module.Credentials.from_service_account_info.return_value = mock_creds
    mock_sa_module.Credentials.from_service_account_file.return_value = mock_creds

    mock_google = MagicMock()
    mock_google.oauth2.service_account = mock_sa_module

    modules = {
        "google": mock_google,
        "google.oauth2": mock_google.oauth2,
        "google.oauth2.service_account": mock_sa_module,
    }
    return modules, mock_sa_module, mock_creds


def _mock_pygsheets_module(mock_gc=None):
    """Create mock pygsheets module."""
    mock_pygsheets = MagicMock()
    if mock_gc is None:
        mock_gc = MagicMock()
    mock_pygsheets.authorize.return_value = mock_gc
    return mock_pygsheets, mock_gc


def _mock_sheets_chain(df=None):
    """Create full mock chain: pygsheets.authorize → open_by_key → worksheet_by_title → wks."""
    if df is None:
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})

    mock_wks = MagicMock()
    mock_wks.get_as_df.return_value = df

    mock_sh = MagicMock()
    mock_sh.worksheet_by_title.return_value = mock_wks

    mock_gc = MagicMock()
    mock_gc.open_by_key.return_value = mock_sh

    return mock_gc, mock_sh, mock_wks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gcp_sheets_env(monkeypatch, bq_connection_json):
    """Set up env vars for a GCP connection used for Sheets."""
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_gcp": "google_cloud_platform"}),
    )
    monkeypatch.setenv("my_gcp", json.dumps(bq_connection_json))


@pytest.fixture
def google_sheets_env(monkeypatch, google_sheets_connection_json):
    """Set up env vars for a standalone google_sheets connection."""
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_sheets": "google_sheets"}),
    )
    monkeypatch.setenv("my_sheets", json.dumps(google_sheets_connection_json))


@pytest.fixture
def postgres_env(monkeypatch, postgres_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_pg": "postgres"}),
    )
    monkeypatch.setenv("my_pg", json.dumps(postgres_connection_json))


@pytest.fixture
def default_conn_env(monkeypatch, bq_connection_json):
    """Set up env with BRUIN_CONNECTION pointing to a GCP connection."""
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"default_gcp": "google_cloud_platform"}),
    )
    monkeypatch.setenv("default_gcp", json.dumps(bq_connection_json))
    monkeypatch.setenv("BRUIN_CONNECTION", "default_gcp")


# ---------------------------------------------------------------------------
# GoogleSheetsConnection
# ---------------------------------------------------------------------------

class TestGoogleSheetsConnection:
    def test_get_connection_returns_google_sheets(self, google_sheets_env):
        conn = get_connection("my_sheets")
        assert isinstance(conn, GoogleSheetsConnection)
        assert conn.type == "google_sheets"
        assert conn.name == "my_sheets"

    def test_repr(self, google_sheets_env):
        conn = get_connection("my_sheets")
        assert repr(conn) == "GoogleSheetsConnection(name='my_sheets')"

    def test_credentials_parsed_from_sa_json(self, google_sheets_env):
        google_mods, mock_sa_mod, mock_creds = _mock_google_modules()

        conn = get_connection("my_sheets")
        with patch.dict(sys.modules, google_mods):
            creds = conn.credentials

        mock_sa_mod.Credentials.from_service_account_info.assert_called_once()
        sa_info = mock_sa_mod.Credentials.from_service_account_info.call_args[0][0]
        assert sa_info["type"] == "service_account"
        assert sa_info["project_id"] == "my-gcp-project"

        # Scopes should be passed
        assert mock_sa_mod.Credentials.from_service_account_info.call_args[1]["scopes"] == [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

    def test_credentials_are_cached(self, google_sheets_env):
        google_mods, mock_sa_mod, _ = _mock_google_modules()

        conn = get_connection("my_sheets")
        with patch.dict(sys.modules, google_mods):
            _ = conn.credentials
            _ = conn.credentials
        mock_sa_mod.Credentials.from_service_account_info.assert_called_once()

    def test_missing_sa_json_raises(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"bad_sheets": "google_sheets"}),
        )
        monkeypatch.setenv("bad_sheets", json.dumps({}))

        conn = get_connection("bad_sheets")
        with pytest.raises(ConnectionParseError, match="no.*service_account_json"):
            _ = conn.credentials

    def test_invalid_sa_json_raises(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"bad_sheets": "google_sheets"}),
        )
        monkeypatch.setenv("bad_sheets", json.dumps({"service_account_json": "not-json"}))

        conn = get_connection("bad_sheets")
        with pytest.raises(ConnectionParseError, match="Failed to parse"):
            _ = conn.credentials

    def test_credentials_from_service_account_file(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"file_sheets": "google_sheets"}),
        )
        monkeypatch.setenv("file_sheets", json.dumps({"service_account_file": "/path/to/sa.json"}))

        google_mods, mock_sa_mod, _ = _mock_google_modules()

        conn = get_connection("file_sheets")
        with patch.dict(sys.modules, google_mods):
            _ = conn.credentials

        mock_sa_mod.Credentials.from_service_account_file.assert_called_once_with(
            "/path/to/sa.json",
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )

    def test_sheets_returns_pygsheets_client(self, google_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_gc, _, _ = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_sheets")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            result = conn.sheets()

        assert result is mock_gc
        mock_pyg.authorize.assert_called_once_with(custom_credentials=mock_creds)

    def test_sheets_client_is_cached(self, google_sheets_env):
        google_mods, _, _ = _mock_google_modules()
        mock_pyg, mock_gc = _mock_pygsheets_module()

        conn = get_connection("my_sheets")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            c1 = conn.sheets()
            c2 = conn.sheets()
        assert c1 is c2
        mock_pyg.authorize.assert_called_once()

    def test_close_clears_cached_state(self, google_sheets_env):
        google_mods, _, _ = _mock_google_modules()
        conn = get_connection("my_sheets")
        with patch.dict(sys.modules, google_mods):
            _ = conn.credentials

        conn.close()
        assert conn._sheets_client is None
        assert conn._credentials is None

    def test_context_manager(self, google_sheets_env):
        with get_connection("my_sheets") as conn:
            assert isinstance(conn, GoogleSheetsConnection)

    def test_client_property_aliases_sheets(self, google_sheets_env):
        conn = get_connection("my_sheets")
        with patch.object(conn, "sheets", return_value=MagicMock()) as mock_sheets:
            result = conn.client
            mock_sheets.assert_called_once()
            assert result is mock_sheets.return_value


# ---------------------------------------------------------------------------
# GCPConnection.sheets() — scoped credentials
# ---------------------------------------------------------------------------

class TestGCPConnectionSheets:
    def test_sheets_adds_scopes(self, gcp_sheets_env):
        google_mods, mock_sa_mod, mock_creds = _mock_google_modules()
        mock_scoped = MagicMock()
        mock_creds.with_scopes.return_value = mock_scoped

        mock_pyg, mock_gc = _mock_pygsheets_module()

        conn = get_connection("my_gcp")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            result = conn.sheets()

        assert result is mock_gc
        mock_creds.with_scopes.assert_called_once_with((
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ))
        mock_pyg.authorize.assert_called_once_with(custom_credentials=mock_scoped)

    def test_sheets_client_is_cached(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_pyg, _ = _mock_pygsheets_module()

        conn = get_connection("my_gcp")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            c1 = conn.sheets()
            c2 = conn.sheets()
        assert c1 is c2
        mock_pyg.authorize.assert_called_once()

    def test_close_clears_sheets_client(self, gcp_sheets_env):
        conn = get_connection("my_gcp")
        conn._sheets_client = MagicMock()

        conn.close()
        assert conn._sheets_client is None


# ---------------------------------------------------------------------------
# _get_sheets_client — connection resolution
# ---------------------------------------------------------------------------

class TestGetSheetsClient:
    def test_gcp_connection_works(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_pyg, _ = _mock_pygsheets_module()

        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            conn, gc = _get_sheets_client("my_gcp")
        assert isinstance(conn, GCPConnection)
        assert gc is not None

    def test_google_sheets_connection_works(self, google_sheets_env):
        google_mods, _, _ = _mock_google_modules()
        mock_pyg, _ = _mock_pygsheets_module()

        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            conn, gc = _get_sheets_client("my_sheets")
        assert isinstance(conn, GoogleSheetsConnection)
        assert gc is not None

    def test_postgres_connection_raises(self, postgres_env):
        with pytest.raises(ConnectionTypeError, match="does not support Google Sheets"):
            _get_sheets_client("my_pg")

    def test_no_connection_no_default_raises(self, monkeypatch):
        monkeypatch.delenv("BRUIN_CONNECTION", raising=False)
        with pytest.raises(ConnectionNotFoundError, match="No connection specified"):
            _get_sheets_client(None)

    def test_default_connection_fallback(self, default_conn_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_pyg, _ = _mock_pygsheets_module()

        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            conn, gc = _get_sheets_client(None)
        assert conn.name == "default_gcp"


# ---------------------------------------------------------------------------
# read_sheet()
# ---------------------------------------------------------------------------

class TestReadSheet:
    def test_read_returns_dataframe(self, gcp_sheets_env):
        expected_df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, mock_sh, mock_wks = _mock_sheets_chain(expected_df)
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            result = read_sheet("spreadsheet_id_123", connection="my_gcp")

        pd.testing.assert_frame_equal(result, expected_df)
        mock_gc.open_by_key.assert_called_once_with("spreadsheet_id_123")
        mock_sh.worksheet_by_title.assert_called_once_with("Sheet1")
        mock_wks.get_as_df.assert_called_once_with(
            numerize=True,
            empty_value="",
            include_tailing_empty=True,
            include_tailing_empty_rows=False,
        )

    def test_read_custom_worksheet(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, mock_sh, _ = _mock_sheets_chain(pd.DataFrame())
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            read_sheet("id123", worksheet="Revenue", connection="my_gcp")
        mock_sh.worksheet_by_title.assert_called_once_with("Revenue")

    def test_read_uses_default_connection(self, default_conn_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, _, _ = _mock_sheets_chain(pd.DataFrame())
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            # No connection= arg — should fall back to BRUIN_CONNECTION
            read_sheet("id123")


# ---------------------------------------------------------------------------
# write_sheet()
# ---------------------------------------------------------------------------

class TestWriteSheet:
    def test_write_clears_then_sets_dataframe(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, mock_sh, mock_wks = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        df = pd.DataFrame({"x": [1, 2, 3]})
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            write_sheet(df, "spreadsheet_id", connection="my_gcp")

        mock_gc.open_by_key.assert_called_once_with("spreadsheet_id")
        mock_sh.worksheet_by_title.assert_called_once_with("Sheet1")

        # clear() must be called before set_dataframe()
        assert mock_wks.clear.call_count == 1
        assert mock_wks.set_dataframe.call_count == 1

        # Verify call order: clear before set_dataframe
        method_names = [c[0] for c in mock_wks.method_calls]
        clear_idx = method_names.index("clear")
        set_idx = method_names.index("set_dataframe")
        assert clear_idx < set_idx

        mock_wks.set_dataframe.assert_called_once_with(
            df, start="A1", fit=True, nan="", escape_formulae=True,
        )

    def test_write_fit_false(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, _, mock_wks = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        df = pd.DataFrame({"x": [1]})
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            write_sheet(df, "id123", connection="my_gcp", fit=False)

        mock_wks.set_dataframe.assert_called_once_with(
            df, start="A1", fit=False, nan="", escape_formulae=True,
        )

    def test_write_custom_worksheet(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, mock_sh, _ = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        df = pd.DataFrame({"x": [1]})
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            write_sheet(df, "id123", worksheet="Output", connection="my_gcp")
        mock_sh.worksheet_by_title.assert_called_once_with("Output")


# ---------------------------------------------------------------------------
# Connection methods — conn.read_sheet() / conn.write_sheet()
# ---------------------------------------------------------------------------

class TestConnectionMethods:
    def test_gcp_conn_read_sheet(self, gcp_sheets_env):
        expected_df = pd.DataFrame({"a": [1]})
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, mock_sh, mock_wks = _mock_sheets_chain(expected_df)
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_gcp")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            result = conn.read_sheet("id123", "Tab1")

        pd.testing.assert_frame_equal(result, expected_df)
        mock_gc.open_by_key.assert_called_once_with("id123")
        mock_sh.worksheet_by_title.assert_called_once_with("Tab1")

    def test_gcp_conn_write_sheet(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, _, mock_wks = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_gcp")
        df = pd.DataFrame({"x": [10]})
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            conn.write_sheet(df, "id456", "Out")

        mock_wks.clear.assert_called_once()
        mock_wks.set_dataframe.assert_called_once_with(
            df, start="A1", fit=True, nan="", escape_formulae=True,
        )

    def test_google_sheets_conn_read_sheet(self, google_sheets_env):
        expected_df = pd.DataFrame({"b": [2]})
        google_mods, _, _ = _mock_google_modules()
        mock_gc, _, mock_wks = _mock_sheets_chain(expected_df)
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_sheets")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            result = conn.read_sheet("id789")

        pd.testing.assert_frame_equal(result, expected_df)

    def test_google_sheets_conn_write_sheet(self, google_sheets_env):
        google_mods, _, _ = _mock_google_modules()
        mock_gc, _, mock_wks = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_sheets")
        df = pd.DataFrame({"z": [99]})
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            conn.write_sheet(df, "id789", fit=False)

        mock_wks.set_dataframe.assert_called_once_with(
            df, start="A1", fit=False, nan="", escape_formulae=True,
        )


# ---------------------------------------------------------------------------
# Import errors
# ---------------------------------------------------------------------------

class TestImportErrors:
    def test_gcp_sheets_missing_pygsheets(self, gcp_sheets_env):
        conn = get_connection("my_gcp")
        # Force credentials so we get past that step
        conn._credentials = MagicMock()

        with patch.dict("sys.modules", {"pygsheets": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[sheets\\]"):
                conn.sheets()

    def test_google_sheets_missing_google_auth(self, google_sheets_env):
        conn = get_connection("my_sheets")

        with patch.dict("sys.modules", {"google.oauth2": None, "google.oauth2.service_account": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[sheets\\]"):
                _ = conn.credentials

    def test_google_sheets_missing_pygsheets(self, google_sheets_env):
        conn = get_connection("my_sheets")
        conn._credentials = MagicMock()

        with patch.dict("sys.modules", {"pygsheets": None}):
            with pytest.raises(ImportError, match="bruin-sdk\\[sheets\\]"):
                conn.sheets()


# ---------------------------------------------------------------------------
# _read_sheet_impl / _write_sheet_impl (internal helpers)
# ---------------------------------------------------------------------------

class TestImplHelpers:
    def test_read_sheet_impl(self, gcp_sheets_env):
        expected_df = pd.DataFrame({"v": [42]})
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, mock_sh, mock_wks = _mock_sheets_chain(expected_df)
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_gcp")
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            result = _read_sheet_impl(conn, "sid", "Tab")

        pd.testing.assert_frame_equal(result, expected_df)
        mock_sh.worksheet_by_title.assert_called_once_with("Tab")

    def test_write_sheet_impl(self, gcp_sheets_env):
        google_mods, _, mock_creds = _mock_google_modules()
        mock_creds.with_scopes.return_value = MagicMock()
        mock_gc, _, mock_wks = _mock_sheets_chain()
        mock_pyg, _ = _mock_pygsheets_module(mock_gc)

        conn = get_connection("my_gcp")
        df = pd.DataFrame({"w": [7]})
        with patch.dict(sys.modules, {**google_mods, "pygsheets": mock_pyg}):
            _write_sheet_impl(conn, df, "sid", "Tab", fit=False)

        mock_wks.clear.assert_called_once()
        mock_wks.set_dataframe.assert_called_once_with(
            df, start="A1", fit=False, nan="", escape_formulae=True,
        )
