import os
import subprocess
from unittest.mock import MagicMock

import pytest

from bruin._cli import _run_cli
from bruin.exceptions import CLIError


@pytest.mark.parametrize("binary", [None, "", "/path with spaces/bruin"])
def test_generic_command_inherits_environment(monkeypatch, binary):
    monkeypatch.delenv("BRUIN_PATH", raising=False)
    if binary is not None:
        monkeypatch.setenv("BRUIN_PATH", binary)
    original_env = dict(os.environ)
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "version output", "diagnostic"))
    monkeypatch.setattr("bruin._cli.subprocess.run", run)

    assert _run_cli(["version"]) == "version output"

    run.assert_called_once_with(
        [binary or "bruin", "version"],
        input=None,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=original_env,
        shell=False,
        timeout=60,
        check=False,
    )
    assert dict(os.environ) == original_env


def test_explicit_environment_is_complete_and_not_modified(monkeypatch):
    monkeypatch.setenv("BRUIN_PATH", "/parent/bruin")
    env = {"BRUIN_PATH": "/child/bruin", "CUSTOM": "child"}
    original_env = env.copy()
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "output", ""))
    monkeypatch.setattr("bruin._cli.subprocess.run", run)

    _run_cli(["validate", "pipeline"], input="input", env=env)

    assert run.call_args.args[0] == ["/child/bruin", "validate", "pipeline"]
    assert run.call_args.kwargs["input"] == "input"
    assert run.call_args.kwargs["env"] == original_env
    assert env == original_env


def test_command_failure_raises_cli_error(monkeypatch):
    run = MagicMock(return_value=subprocess.CompletedProcess([], 2, "", "invalid pipeline"))
    monkeypatch.setattr("bruin._cli.subprocess.run", run)

    with pytest.raises(CLIError, match=r"exit 2.*invalid pipeline"):
        _run_cli(["validate", "pipeline"])
