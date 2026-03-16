# Development

Always run `uv run ruff format --check .` and `uv run python -m pytest tests/ -q` after making changes.

# Publishing

Bump `version` in `pyproject.toml` before creating a release. The publish workflow triggers on GitHub releases, not tags alone.
