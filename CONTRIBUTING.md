# Contributing

## Setup

```bash
pip install -e ".[dev]"
```

## Building

The project uses [hatchling](https://hatch.pypa.io/) as the build backend. To build the package locally:

```bash
pip install build
python -m build
```

This creates both a source distribution and wheel in the `dist/` directory:

```
dist/
  bruin_sdk-0.X.Y.tar.gz
  bruin_sdk-0.X.Y-py3-none-any.whl
```

To install from the built wheel:

```bash
pip install dist/bruin_sdk-0.X.Y-py3-none-any.whl
```

## Tests

### Unit tests

```bash
pytest tests/ -v
```

### Integration tests

Integration tests live under `tests/integration/` and are marked with `@pytest.mark.integration`.

**DuckDB** tests run locally with no credentials:

```bash
pytest tests/integration/test_duckdb.py -v
```

**BigQuery** tests require GCP credentials:

```bash
# Using Application Default Credentials (gcloud CLI):
BRUIN_TEST_BQ_PROJECT_ID=your-project pytest tests/integration/test_bigquery.py -v

# Using a service account:
BRUIN_TEST_BQ_PROJECT_ID=your-project \
BRUIN_TEST_BQ_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}' \
pytest tests/integration/test_bigquery.py -v
```

**Snowflake** tests require Snowflake credentials:

```bash
BRUIN_TEST_SF_ACCOUNT=xy12345.us-east-1 \
BRUIN_TEST_SF_USERNAME=user \
BRUIN_TEST_SF_PASSWORD=pass \
BRUIN_TEST_SF_DATABASE=mydb \
BRUIN_TEST_SF_WAREHOUSE=mywh \
pytest tests/integration/test_snowflake.py -v
```

To skip integration tests:

```bash
pytest -m "not integration"
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
