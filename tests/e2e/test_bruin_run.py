"""End-to-end tests that run actual bruin pipelines with the Python SDK.

These tests require a working bruin binary. Set BRUIN_PATH to point at a
specific binary, or they'll auto-discover from the sibling repo or system PATH.

Run:
    BRUIN_PATH=/path/to/bruin pytest tests/e2e/ -v
    # or, if bin/bruin exists in sibling bruin repo:
    pytest tests/e2e/ -v
"""

import json
import os
import subprocess
import textwrap

import pytest

# Root of the bruin-python-package (contains src/bruin/)
SDK_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def pipeline_dir(tmp_path):
    """Create a minimal bruin pipeline structure in a temp directory."""

    # bruin requires a git repo
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=str(tmp_path),
        capture_output=True,
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        },
    )

    # .bruin.yml (project config — no connections needed for context-only test)
    (tmp_path / ".bruin.yml").write_text(
        textwrap.dedent("""\
        environments:
          default:
            connections: {}
    """)
    )

    # pipeline.yml
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "pipeline.yml").write_text(
        textwrap.dedent("""\
        name: test_pipeline
        schedule: daily
    """)
    )

    assets_dir = pipeline_dir / "assets"
    assets_dir.mkdir()

    # requirements.txt pointing to the local SDK so bruin installs it
    (tmp_path / "requirements.txt").write_text(f"{SDK_ROOT}\n")

    return tmp_path, pipeline_dir, assets_dir


class TestContextEnvVars:
    """Verify that bruin injects BRUIN_* env vars and the SDK reads them."""

    def test_context_available_in_asset(self, bruin_bin, pipeline_dir):
        root, pipe_dir, assets_dir = pipeline_dir

        # A Python asset that writes context values to a file
        output_file = root / "output.json"
        asset_code = textwrap.dedent(f'''\
            """ @bruin

            name: test_context
            type: python

            @bruin """

            import json
            import os
            from bruin import context

            result = {{
                "asset_name": context.asset_name,
                "pipeline": context.pipeline,
                "start_date": str(context.start_date) if context.start_date else None,
                "end_date": str(context.end_date) if context.end_date else None,
                "is_full_refresh": context.is_full_refresh,
                "has_bruin_asset": "BRUIN_ASSET" in os.environ,
                "has_bruin_this": "BRUIN_THIS" in os.environ,
            }}

            with open("{output_file}", "w") as f:
                json.dump(result, f)
        ''')
        (assets_dir / "test_context.py").write_text(asset_code)

        # Run bruin
        result = subprocess.run(
            [
                bruin_bin,
                "run",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-02",
                str(pipe_dir / "assets" / "test_context.py"),
            ],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=120,
        )

        assert result.returncode == 0, (
            f"bruin run failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert output_file.exists(), (
            f"Asset did not produce output file.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        output = json.loads(output_file.read_text())
        assert output["asset_name"] == "test_context"
        assert output["pipeline"] == "test_pipeline"
        assert output["start_date"] == "2024-06-01"
        assert output["end_date"] == "2024-06-02"
        assert output["has_bruin_asset"] is True
        assert output["has_bruin_this"] is True


class TestConnectionEnvVar:
    """Verify BRUIN_CONNECTION is injected when asset has a connection field."""

    def test_bruin_connection_injected(self, bruin_bin, pipeline_dir):
        root, pipe_dir, assets_dir = pipeline_dir

        output_file = root / "conn_output.json"
        # Use a secret injection instead of a real connection to avoid
        # bruin trying to validate credentials at init time.
        asset_code = textwrap.dedent(f'''\
            """ @bruin

            name: test_conn
            type: python
            connection: my_duckdb

            @bruin """

            import json
            import os
            from bruin import context

            result = {{
                "connection": context.connection,
                "has_bruin_connection": "BRUIN_CONNECTION" in os.environ,
            }}

            with open("{output_file}", "w") as f:
                json.dump(result, f)
        ''')
        (assets_dir / "test_conn.py").write_text(asset_code)

        # Use a DuckDB connection — no external credentials needed
        (root / ".bruin.yml").write_text(
            textwrap.dedent("""\
            environments:
              default:
                connections:
                  duckdb:
                    - name: my_duckdb
                      path: ":memory:"
        """)
        )

        result = subprocess.run(
            [
                bruin_bin,
                "run",
                "--start-date",
                "2024-06-01",
                "--end-date",
                "2024-06-02",
                str(pipe_dir / "assets" / "test_conn.py"),
            ],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=120,
        )

        assert result.returncode == 0, (
            f"bruin run failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert output_file.exists(), (
            f"Asset did not produce output file.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        output = json.loads(output_file.read_text())
        assert output["connection"] == "my_duckdb"
        assert output["has_bruin_connection"] is True
