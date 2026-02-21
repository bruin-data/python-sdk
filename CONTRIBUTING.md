# Contributing

## Setup

```bash
pip install -e ".[dev]"
```

## Tests

```bash
pytest tests/ -v
```

## Releasing

Releases are automated via GitHub Actions. To publish a new version:

1. Bump `version` in both `pyproject.toml` and `src/bruin/__init__.py`
2. Commit and push to `main`
3. Create a GitHub release:
   ```bash
   git tag v0.X.Y && git push origin v0.X.Y
   gh release create v0.X.Y --title "v0.X.Y" --notes "Release notes here"
   ```
4. The `publish.yml` workflow automatically builds and publishes to PyPI via trusted publishing (OIDC)
