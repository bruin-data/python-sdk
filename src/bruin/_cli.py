"""Shared process boundary for Bruin CLI commands."""

import os
import subprocess

from bruin.exceptions import CLIError


def _run_cli(
    args: list[str], *, input: str | None = None, env: dict[str, str] | None = None
) -> str:
    """Run CLI arguments without a shell and return stdout, or raise CLIError.

    When supplied, env is the complete child environment, as in subprocess.run.
    Otherwise the current environment is inherited. Neither is modified.
    """
    if env is None:
        env = os.environ.copy()
    binary = env.get("BRUIN_PATH") or "bruin"
    try:
        result = subprocess.run(
            [binary, *args],
            input=input,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            shell=False,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CLIError(
            f"Bruin CLI binary '{binary}' not found. Install Bruin and put it on PATH, "
            "or set BRUIN_PATH to its executable."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CLIError("Bruin CLI command timed out after 60s.") from exc
    except OSError as exc:
        raise CLIError(f"Cannot start Bruin CLI '{binary}': {exc}") from exc

    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no error output"
        raise CLIError(f"Bruin CLI command failed (exit {result.returncode}): {detail}")
    return result.stdout
