"""Render query SQL with the Bruin CLI; database execution stays in Python."""

import json
import os

from bruin._cli import _run_cli
from bruin.exceptions import CLIError, QueryError


def _render_sql(sql: str, connection: str) -> str:
    env = os.environ.copy()
    env["BRUIN_CONNECTION"] = connection
    # shortcut: provisional stdin contract; verify against the CLI change before release.
    command = [
        "render",
        "--stdin",
        "--connection",
        connection,
        "--raw-query",
        "--output",
        "json",
    ]
    if env.get("BRUIN_ENVIRONMENT"):
        command.extend(["--environment", env["BRUIN_ENVIRONMENT"]])
    for flag, keys in (
        ("--start-date", ("BRUIN_START_DATETIME", "BRUIN_START_DATE")),
        ("--end-date", ("BRUIN_END_DATETIME", "BRUIN_END_DATE")),
    ):
        value = next((env[key] for key in keys if env.get(key)), None)
        if value:
            command.extend([flag, value])
    if env.get("BRUIN_FULL_REFRESH") == "1":
        command.append("--full-refresh")
    # Use the same typed variables exposed by bruin.context.
    from bruin._context import context

    for key, value in context.vars.items():
        command.extend(["--var", f"{key}={json.dumps(value)}"])

    try:
        output = _run_cli(command, input=sql, env=env)
    except CLIError as exc:
        raise QueryError(
            f"SQL rendering failed on connection '{connection}': {exc}\nA CLI supporting "
            "'render --stdin --connection ... --raw-query --output json' "
            "is required; upgrade the CLI if these options are unsupported."
        ) from exc
    try:
        payload = json.loads(output)
    except (ValueError, TypeError) as exc:
        raise QueryError(
            "Invalid Bruin render output: expected a JSON object containing a 'query' string. "
            "Check that the CLI supports stdin query rendering."
        ) from exc
    rendered = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(rendered, str) or not rendered.strip():
        raise QueryError("Invalid Bruin render output: expected a non-empty 'query' string.")
    return rendered
