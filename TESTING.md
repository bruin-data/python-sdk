# Testing Strategy

## Principle

Every module has a clear split:
- **Pure logic** (parsing JSON, building CLI args, type conversion) → test directly
- **External calls** (subprocess, API clients) → mock at the boundary

No real Bruin CLI, database, or API calls in unit tests. Tests run in milliseconds.

## Module-by-Module

### Context (`_context.py`)

Easiest to test. It just reads env vars and converts types. Set env vars, assert output.

```python
import os
from datetime import date, datetime

def test_start_date(monkeypatch):
    monkeypatch.setenv("BRUIN_START_DATE", "2024-01-15")
    assert context.start_date == date(2024, 1, 15)

def test_start_datetime(monkeypatch):
    monkeypatch.setenv("BRUIN_START_DATETIME", "2024-01-15T13:45:30")
    assert context.start_datetime == datetime(2024, 1, 15, 13, 45, 30)

def test_vars(monkeypatch):
    monkeypatch.setenv("BRUIN_VARS", '{"segment": "enterprise", "horizon": 30}')
    assert context.vars["segment"] == "enterprise"
    assert context.vars["horizon"] == 30

def test_is_full_refresh_true(monkeypatch):
    monkeypatch.setenv("BRUIN_FULL_REFRESH", "1")
    assert context.is_full_refresh is True

def test_is_full_refresh_false(monkeypatch):
    monkeypatch.delenv("BRUIN_FULL_REFRESH", raising=False)
    assert context.is_full_refresh is False

def test_missing_env_returns_none(monkeypatch):
    monkeypatch.delenv("BRUIN_START_DATE", raising=False)
    assert context.start_date is None

def test_empty_vars_returns_empty_dict(monkeypatch):
    monkeypatch.delenv("BRUIN_VARS", raising=False)
    assert context.vars == {}
```

No mocks needed. Just `monkeypatch.setenv`.

---

### Query (`_query.py`)

Two things to test:
1. Are we building the right CLI command?
2. Are we parsing the JSON output into a DataFrame correctly?

```python
import pandas as pd
from unittest.mock import patch, MagicMock

# Test: CLI args are built correctly
def test_query_builds_correct_command():
    mock_result = MagicMock()
    mock_result.stdout = '[{"id": 1, "name": "alice"}]'
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        df = query("SELECT * FROM users", connection="my_bq")

        args = mock_run.call_args[0][0]
        assert "bruin" in args
        assert "query" in args
        assert "--connection" in args
        assert "my_bq" in args
        assert "--output" in args
        assert "json" in args

# Test: limit and timeout are passed through
def test_query_passes_limit_and_timeout():
    mock_result = MagicMock(stdout="[]", returncode=0)

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        query("SELECT 1", connection="x", limit=10, timeout=30)
        args = mock_run.call_args[0][0]
        assert "--limit" in args
        assert "10" in args
        assert "--timeout" in args
        assert "30" in args

# Test: JSON output is parsed into a DataFrame
def test_query_returns_dataframe():
    json_output = '[{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]'
    mock_result = MagicMock(stdout=json_output, returncode=0)

    with patch("subprocess.run", return_value=mock_result):
        df = query("SELECT * FROM users", connection="my_bq")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["id", "name"]

# Test: empty result
def test_query_empty_result():
    mock_result = MagicMock(stdout="[]", returncode=0)

    with patch("subprocess.run", return_value=mock_result):
        df = query("SELECT * FROM users WHERE 1=0", connection="my_bq")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

# Test: CLI error raises exception
def test_query_cli_error():
    mock_result = MagicMock(stdout="", stderr="connection not found", returncode=1)

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(BruinQueryError, match="connection not found"):
            query("SELECT 1", connection="nonexistent")
```

Mock boundary: `subprocess.run`. Everything above it (arg building) and below it (JSON parsing) is tested directly.

---

### Connection (`_connection.py`)

Split into two testable parts:
1. **Parsing**: env var JSON → structured connection dict
2. **Client creation**: structured dict → native client (mock the client constructor)

```python
# --- Parsing tests (no mocks needed) ---

def test_parse_bigquery_connection(monkeypatch):
    conn_json = json.dumps({
        "service_account_json": json.dumps({"type": "service_account", "project_id": "my-proj"}),
        "project_id": "my-proj"
    })
    monkeypatch.setenv("my_bq", conn_json)

    conn = get_connection("my_bq")
    assert conn.raw["project_id"] == "my-proj"

def test_parse_postgres_connection(monkeypatch):
    conn_json = json.dumps({
        "host": "localhost",
        "port": 5432,
        "database": "mydb",
        "username": "user",
        "password": "pass"
    })
    monkeypatch.setenv("my_pg", conn_json)

    conn = get_connection("my_pg")
    assert conn.raw["host"] == "localhost"
    assert conn.raw["port"] == 5432

def test_connection_not_found(monkeypatch):
    monkeypatch.delenv("nonexistent", raising=False)
    with pytest.raises(ConnectionNotFoundError):
        get_connection("nonexistent")

def test_invalid_json_raises_error(monkeypatch):
    monkeypatch.setenv("bad_conn", "not json")
    with pytest.raises(ConnectionParseError):
        get_connection("bad_conn")

# --- Client creation tests (mock the client constructor) ---

def test_bigquery_client_creation(monkeypatch):
    conn_json = json.dumps({
        "service_account_json": json.dumps({"type": "service_account", "project_id": "p"}),
        "project_id": "p"
    })
    monkeypatch.setenv("my_bq", conn_json)

    with patch("google.cloud.bigquery.Client.from_service_account_info") as mock_bq:
        mock_bq.return_value = MagicMock()
        conn = get_connection("my_bq")
        client = conn.client
        mock_bq.assert_called_once()

def test_client_is_lazy(monkeypatch):
    conn_json = json.dumps({"host": "localhost", "port": 5432})
    monkeypatch.setenv("my_pg", conn_json)

    with patch("psycopg2.connect") as mock_pg:
        conn = get_connection("my_pg")
        mock_pg.assert_not_called()  # not created yet
        _ = conn.client
        mock_pg.assert_called_once()  # now created
```

---

### Slack (`slack.py`)

Mock `requests.post`. Test that the right URL and payload are sent.

```python
def test_slack_send_webhook(monkeypatch):
    monkeypatch.setenv("slack_conn", "https://hooks.slack.com/services/T00/B00/xxx")

    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        slack.send("slack_conn", "hello")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "hello" in str(call_kwargs)

def test_slack_send_missing_connection(monkeypatch):
    monkeypatch.delenv("missing", raising=False)
    with pytest.raises(ConnectionNotFoundError):
        slack.send("missing", "hello")
```

---

### Google Sheets (`gsheets.py`)

Mock `pygsheets.authorize` and the worksheet methods.

```python
def test_gsheets_write(monkeypatch):
    # Setup GCP connection env var
    conn_json = json.dumps({
        "service_account_json": json.dumps({"type": "service_account"}),
        "project_id": "p"
    })
    monkeypatch.setenv("gcp_conn", conn_json)

    mock_wks = MagicMock()
    mock_sh = MagicMock()
    mock_sh.worksheet_by_title.return_value = mock_wks
    mock_gc = MagicMock()
    mock_gc.open_by_key.return_value = mock_sh

    with patch("pygsheets.authorize", return_value=mock_gc):
        df = pd.DataFrame({"a": [1, 2]})
        gsheets.write(df, "gcp_conn", spreadsheet_id="abc", sheet="Sheet1")

        mock_wks.clear.assert_called_once()
        mock_wks.set_dataframe.assert_called_once()
```

---

### CLI Wrappers (`pipeline.py`, `connections.py`)

Same pattern as query: mock `subprocess.run`, verify args.

```python
def test_pipeline_run():
    mock_result = MagicMock(stdout='{"status": "success"}', returncode=0)

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        pipeline.run("path/to/pipeline", environment="production")
        args = mock_run.call_args[0][0]
        assert "run" in args
        assert "--environment" in args
        assert "production" in args

def test_connections_list():
    mock_result = MagicMock(stdout='[{"name": "my_bq", "type": "bigquery"}]', returncode=0)

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        conns = connections.list()
        assert len(conns) == 1
        assert conns[0]["name"] == "my_bq"
```

---

## Test Fixtures

Reusable connection JSON payloads that mirror real Bruin connections. Keeps tests DRY.

```python
# conftest.py

import pytest
import json

@pytest.fixture
def bigquery_conn_env(monkeypatch):
    """Sets up a realistic BigQuery connection env var."""
    conn = {
        "service_account_json": json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key123",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
        }),
        "project_id": "test-project"
    }
    monkeypatch.setenv("test_bigquery", json.dumps(conn))

@pytest.fixture
def postgres_conn_env(monkeypatch):
    """Sets up a realistic Postgres connection env var."""
    conn = {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "username": "testuser",
        "password": "testpass"
    }
    monkeypatch.setenv("test_postgres", json.dumps(conn))

@pytest.fixture
def snowflake_conn_env(monkeypatch):
    """Sets up a realistic Snowflake connection env var."""
    conn = {
        "account": "xy12345.us-east-1",
        "username": "testuser",
        "password": "testpass",
        "warehouse": "COMPUTE_WH",
        "database": "TESTDB",
        "schema": "PUBLIC",
        "role": "SYSADMIN"
    }
    monkeypatch.setenv("test_snowflake", json.dumps(conn))

@pytest.fixture
def aws_conn_env(monkeypatch):
    """Sets up a realistic AWS connection env var."""
    conn = {
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "us-east-1",
        "query_results_path": "s3://my-bucket/results/"
    }
    monkeypatch.setenv("test_aws", json.dumps(conn))

@pytest.fixture
def slack_conn_env(monkeypatch):
    """Sets up a Slack webhook connection env var."""
    monkeypatch.setenv("test_slack", "https://hooks.slack.com/services/T00/B00/xxxx")

@pytest.fixture
def bruin_context_env(monkeypatch):
    """Sets up a full Bruin runtime context."""
    monkeypatch.setenv("BRUIN_START_DATE", "2024-01-15")
    monkeypatch.setenv("BRUIN_END_DATE", "2024-01-16")
    monkeypatch.setenv("BRUIN_START_DATETIME", "2024-01-15T13:45:30")
    monkeypatch.setenv("BRUIN_END_DATETIME", "2024-01-16T00:00:00")
    monkeypatch.setenv("BRUIN_EXECUTION_DATE", "2024-01-15")
    monkeypatch.setenv("BRUIN_RUN_ID", "run-abc-123")
    monkeypatch.setenv("BRUIN_PIPELINE", "my_pipeline")
    monkeypatch.setenv("BRUIN_THIS", "tier1.my_asset")
    monkeypatch.setenv("BRUIN_FULL_REFRESH", "1")
    monkeypatch.setenv("BRUIN_VARS", '{"segment": "enterprise", "horizon": 30}')

@pytest.fixture
def mock_bruin_cli():
    """Mocks subprocess.run for bruin CLI calls."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="[]", stderr="", returncode=0)
        yield mock_run
```

## Test Organization

```
tests/
  conftest.py              # shared fixtures above
  test_context.py          # context parsing (monkeypatch only, no mocks)
  test_query.py            # query CLI wrapper (mock subprocess)
  test_connection.py       # connection parsing + client creation
  test_slack.py            # slack helper
  test_gsheets.py          # google sheets helper
  test_pipeline.py         # CLI wrappers
  test_connections_cmd.py  # connections list/test
  test_exceptions.py       # error handling and messages
```

## Running Tests

```bash
# all tests
pytest

# single module
pytest tests/test_context.py

# with coverage
pytest --cov=bruin --cov-report=term-missing
```

## What We Do NOT Test

- Real database connections (that's Bruin CLI's job)
- Real Bruin CLI execution (we trust it works)
- Platform client library internals (google-cloud-bigquery, psycopg2, etc.)

We only test our logic: parsing, arg building, type conversion, error handling.
