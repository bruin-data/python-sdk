import json
import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bruin import get_connection, query


@pytest.fixture
def pg_env(monkeypatch, postgres_connection_json):
    monkeypatch.setenv(
        "BRUIN_CONNECTION_TYPES",
        json.dumps({"my_pg": "postgres"}),
    )
    monkeypatch.setenv("my_pg", json.dumps(postgres_connection_json))
    monkeypatch.setenv("BRUIN_ASSET", "test_asset")
    monkeypatch.setenv("BRUIN_PIPELINE", "test_pipeline")
    monkeypatch.setenv("BRUIN_CONNECTION", "my_pg")


class TestConnectionLogging:
    def test_get_connection_logs_resolution(self, pg_env, caplog):
        with caplog.at_level(logging.DEBUG, logger="bruin"):
            get_connection("my_pg")

        assert any("Resolved connection 'my_pg'" in m for m in caplog.messages)
        assert any("type=postgres" in m for m in caplog.messages)

    def test_client_creation_logged(self, pg_env, caplog):
        conn = get_connection("my_pg")
        with caplog.at_level(logging.DEBUG, logger="bruin"), \
             patch("psycopg2.connect", return_value=MagicMock()):
            _ = conn.client

        assert any("Creating postgres client" in m for m in caplog.messages)

    def test_close_logged(self, pg_env, caplog):
        conn = get_connection("my_pg")
        with patch("psycopg2.connect", return_value=MagicMock()):
            _ = conn.client

        with caplog.at_level(logging.DEBUG, logger="bruin"):
            conn.close()

        assert any("Closing client" in m for m in caplog.messages)

    def test_no_log_when_level_above_debug(self, pg_env, caplog):
        with caplog.at_level(logging.INFO, logger="bruin"):
            get_connection("my_pg")

        assert len(caplog.messages) == 0


class TestQueryLogging:
    def test_select_logs_execution_and_result(self, pg_env, caplog):
        mock_df = pd.DataFrame({"id": [1, 2, 3]})

        with caplog.at_level(logging.DEBUG, logger="bruin"), \
             patch("psycopg2.connect", return_value=MagicMock()), \
             patch("pandas.read_sql", return_value=mock_df):
            query("SELECT * FROM t")

        messages = " ".join(caplog.messages)
        assert "Executing query on 'my_pg'" in messages
        assert "returns_data=True" in messages
        assert "3 rows x 1 cols" in messages

    def test_dml_logs_no_result_set(self, pg_env, caplog):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with caplog.at_level(logging.DEBUG, logger="bruin"), \
             patch("psycopg2.connect", return_value=mock_conn):
            query("INSERT INTO t VALUES (1)")

        messages = " ".join(caplog.messages)
        assert "Executing query on 'my_pg'" in messages
        assert "returns_data=False" in messages
        assert "no result set" in messages


class TestContextLogging:
    def test_date_parsing_logged(self, monkeypatch, caplog):
        monkeypatch.setenv("BRUIN_START_DATE", "2025-01-15")

        from bruin import context
        with caplog.at_level(logging.DEBUG, logger="bruin"):
            context.start_date

        assert any("BRUIN_START_DATE=2025-01-15" in m for m in caplog.messages)
