import json
from unittest.mock import patch

import pytest

from bruin import get_connection, query
from bruin.exceptions import (
    BruinError,
    ConnectionNotFoundError,
    ConnectionParseError,
    ConnectionTypeError,
    QueryError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_bruin_error(self):
        assert issubclass(ConnectionNotFoundError, BruinError)
        assert issubclass(ConnectionParseError, BruinError)
        assert issubclass(ConnectionTypeError, BruinError)
        assert issubclass(QueryError, BruinError)

    def test_bruin_error_inherits_from_exception(self):
        assert issubclass(BruinError, Exception)

    def test_can_catch_with_base_class(self):
        with pytest.raises(BruinError):
            raise ConnectionNotFoundError("test")


class TestConnectionNotFoundError:
    def test_missing_connection_types_env(self, monkeypatch):
        monkeypatch.delenv("BRUIN_CONNECTION_TYPES", raising=False)
        with pytest.raises(ConnectionNotFoundError):
            get_connection("anything")

    def test_name_not_in_type_map(self, monkeypatch):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", json.dumps({"a": "postgres"}))
        with pytest.raises(ConnectionNotFoundError, match="not found"):
            get_connection("missing")

    def test_error_lists_available_connections(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"alpha": "postgres", "beta": "snowflake"}),
        )
        with pytest.raises(ConnectionNotFoundError, match="alpha") as exc_info:
            get_connection("missing")
        assert "beta" in str(exc_info.value)


class TestConnectionParseError:
    def test_invalid_connection_types_json(self, monkeypatch):
        monkeypatch.setenv("BRUIN_CONNECTION_TYPES", "{bad json")
        with pytest.raises(ConnectionParseError, match="BRUIN_CONNECTION_TYPES"):
            get_connection("x")

    def test_invalid_connection_payload(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_pg": "postgres"}),
        )
        monkeypatch.setenv("my_pg", "{bad json")
        with pytest.raises(ConnectionParseError, match="connection JSON"):
            get_connection("my_pg")


class TestConnectionTypeError:
    def test_generic_client_access(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"webhook": "generic"}),
        )
        monkeypatch.setenv("webhook", "https://example.com/hook")
        conn = get_connection("webhook")
        with pytest.raises(ConnectionTypeError, match="generic"):
            _ = conn.client

    def test_unsupported_type_client_access(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"my_conn": "exotic_db"}),
        )
        monkeypatch.setenv("my_conn", json.dumps({"host": "x"}))
        conn = get_connection("my_conn")
        with pytest.raises(ConnectionTypeError, match="Unsupported"):
            _ = conn.client


class TestQueryError:
    def test_wraps_underlying_exception(self, monkeypatch, snowflake_connection_json):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"sf": "snowflake"}),
        )
        monkeypatch.setenv("sf", json.dumps(snowflake_connection_json))

        with patch(
            "bruin._connection._create_snowflake",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(QueryError, match="boom") as exc_info:
                query("SELECT 1", "sf")
            assert exc_info.value.__cause__ is not None

    def test_generic_connection_query_raises_type_error(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_CONNECTION_TYPES",
            json.dumps({"hook": "generic"}),
        )
        monkeypatch.setenv("hook", "https://example.com")
        with pytest.raises(ConnectionTypeError, match="generic"):
            query("SELECT 1", "hook")
