"""SDK boundary tests for the provisional CLI contract, not live CLI validation."""

import json
import os
import subprocess
from unittest.mock import MagicMock

import pandas as pd
import pytest

from bruin import get_connection, query
from bruin._render import _render_sql
from bruin.exceptions import QueryError


@pytest.fixture(autouse=True)
def clean_context(monkeypatch):
    for key in os.environ:
        if key.startswith("BRUIN_"):
            monkeypatch.delenv(key)


@pytest.fixture
def cli(monkeypatch):
    run = MagicMock(
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=json.dumps({"query": "SELECT 42 AS value"}), stderr=""
        )
    )
    monkeypatch.setattr("bruin._cli.subprocess.run", run)
    return run


def test_render_transfers_environment_and_context(monkeypatch, cli):
    context = {
        "BRUIN_PATH": "/path with spaces/bruin",
        "BRUIN_CONNECTION": "asset_default",
        "BRUIN_ENVIRONMENT": "staging",
        "BRUIN_CONFIG_FILE": "/project/.bruin.yml",
        "BRUIN_CONNECTION_TYPES": '{"selected":"sqlite"}',
        "BRUIN_START_DATE": "2026-10-01",
        "BRUIN_START_DATETIME": "2026-10-01T12:30:00",
        "BRUIN_END_DATE": "2026-10-02",
        "BRUIN_FULL_REFRESH": "1",
        "BRUIN_VARS": '{"count":"2","region":"EU","enabled":true,"ids":[1,2]}',
        "BRUIN_VARS_SCHEMA": '{"count":{"type":"integer"}}',
        "BRUIN_THIS": "analytics.output",
        "BRUIN_ASSET": "analytics.output",
        "BRUIN_PIPELINE": "analytics",
        "BRUIN_EXECUTION_DATETIME": "2026-10-02T15:00:00",
        "BRUIN_RUN_ID": "original-run",
        "selected": '{"path":":memory:"}',
    }
    for key, value in context.items():
        monkeypatch.setenv(key, value)
    original_env = dict(os.environ)
    sql = "SELECT '{{ start_date }}', '$(echo unsafe)'"

    assert _render_sql(sql, "selected") == "SELECT 42 AS value"

    cli.assert_called_once_with(
        [
            "/path with spaces/bruin",
            "render",
            "--stdin",
            "--connection",
            "selected",
            "--raw-query",
            "--output",
            "json",
            "--environment",
            "staging",
            "--start-date",
            "2026-10-01T12:30:00",
            "--end-date",
            "2026-10-02",
            "--full-refresh",
            "--var",
            "count=2",
            "--var",
            'region="EU"',
            "--var",
            "enabled=true",
            "--var",
            "ids=[1, 2]",
        ],
        input=sql,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env={**original_env, "BRUIN_CONNECTION": "selected"},
        shell=False,
        timeout=60,
        check=False,
    )
    assert dict(os.environ) == original_env


def test_render_without_context_uses_cli_defaults(cli):
    _render_sql("SELECT 1", "selected")
    assert cli.call_args.args[0] == [
        "bruin",
        "render",
        "--stdin",
        "--connection",
        "selected",
        "--raw-query",
        "--output",
        "json",
    ]


@pytest.mark.parametrize("api", ["default", "explicit", "bound"])
@pytest.mark.parametrize(
    "rendered,expected", [("SELECT 42 AS value", 42), ("CREATE TABLE t(x)", None)]
)
def test_rendered_sql_reaches_existing_client(monkeypatch, cli, api, rendered, expected):
    monkeypatch.setenv("BRUIN_CONNECTION_TYPES", '{"selected":"sqlite"}')
    monkeypatch.setenv("selected", '{"path":":memory:"}')
    monkeypatch.setenv("BRUIN_CONNECTION", "selected" if api == "default" else "other")
    conn = get_connection("selected")
    client = MagicMock()
    cursor = client.cursor.return_value
    cursor.description = [("value",)] if expected is not None else None
    cursor.fetchall.return_value = [(42,)]
    conn._client = client
    monkeypatch.setattr(
        "bruin._query.get_connection", lambda name: conn if name == conn.name else None
    )
    cli.return_value.stdout = json.dumps({"query": rendered})

    if api == "bound":
        result = conn.query("{{ unrendered }}")
    elif api == "explicit":
        result = query("{{ unrendered }}", connection="selected")
    else:
        result = query("{{ unrendered }}")

    executed = cursor.execute.call_args.args[0]
    assert executed.startswith("-- @bruin.config:")
    assert executed.split("\n", 1)[1] == rendered
    assert conn._client is client
    assert cli.call_args.kwargs["env"]["BRUIN_CONNECTION"] == "selected"
    if expected is None:
        assert result is None
        client.commit.assert_called_once()
    else:
        pd.testing.assert_frame_equal(result, pd.DataFrame({"value": [expected]}))
        client.commit.assert_not_called()


@pytest.mark.parametrize(
    "response,message",
    [
        (subprocess.CompletedProcess([], 1, "", "Jinja failed"), "Jinja failed"),
        (subprocess.CompletedProcess([], 2, "unknown flag: --stdin", ""), "upgrade the CLI"),
        (subprocess.CompletedProcess([], 1, "", ""), "no error output"),
        (subprocess.CompletedProcess([], 0, "plain SQL", ""), "expected a JSON object"),
        (subprocess.CompletedProcess([], 0, '{"query":null}', ""), "non-empty 'query'"),
        (subprocess.CompletedProcess([], 0, '{"query":"  "}', ""), "non-empty 'query'"),
        (subprocess.CompletedProcess([], 0, '{"query":[]}', ""), "non-empty 'query'"),
        (subprocess.CompletedProcess([], 0, "[]", ""), "non-empty 'query'"),
        (subprocess.CompletedProcess([], 0, '{"error":"failed"}', ""), "non-empty 'query'"),
        (FileNotFoundError(), "not found.*BRUIN_PATH"),
        (PermissionError("not executable"), "Cannot start Bruin CLI"),
        (subprocess.TimeoutExpired("bruin", 60), "timed out"),
    ],
)
def test_render_failure_never_initializes_client(monkeypatch, cli, response, message):
    monkeypatch.setenv("BRUIN_CONNECTION_TYPES", '{"selected":"sqlite"}')
    monkeypatch.setenv("selected", '{"path":":memory:"}')
    if isinstance(response, Exception):
        cli.side_effect = response
    else:
        cli.return_value = response
    factory = MagicMock()
    monkeypatch.setattr("bruin._connection._create_client", factory)

    with pytest.raises(QueryError, match=message):
        query("SELECT original_sql", "selected")

    factory.assert_not_called()
    cli.assert_called_once()


def test_real_subprocess_stdin_to_python_database(monkeypatch, tmp_path):
    # This executable is a contract stub, deliberately not a live Bruin CLI test.
    import sys

    binary = tmp_path / "render stub"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "assert sys.argv[1:] == ['render', '--stdin', '--connection', 'selected', "
        "'--raw-query', '--output', 'json', '--environment', 'staging']\n"
        "assert sys.stdin.read() == \"SELECT '{{ vars.n }}' AS value; -- $(exit 99)\"\n"
        "assert os.environ['BRUIN_CONNECTION'] == 'selected'\n"
        "assert os.environ['BRUIN_RUN_ID'] == 'test-run'\n"
        "print(json.dumps({'query': 'SELECT 42 AS value'}))\n"
    )
    binary.chmod(0o755)
    monkeypatch.setenv("BRUIN_PATH", str(binary))
    monkeypatch.setenv("BRUIN_ENVIRONMENT", "staging")
    monkeypatch.setenv("BRUIN_RUN_ID", "test-run")
    monkeypatch.setenv("BRUIN_CONNECTION_TYPES", '{"selected":"sqlite"}')
    monkeypatch.setenv("selected", '{"path":":memory:"}')

    result = query("SELECT '{{ vars.n }}' AS value; -- $(exit 99)", "selected")

    pd.testing.assert_frame_equal(result, pd.DataFrame({"value": [42]}))
