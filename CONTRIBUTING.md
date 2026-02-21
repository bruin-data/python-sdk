# Contributing

## Setup

```bash
make setup
```

## Building

```bash
make build
```

This creates both a source distribution and wheel in `dist/`.

## Tests

```bash
make test          # all tests
make test-unit     # unit tests only (skips integration)
make test-integration  # integration tests only
```

### Integration tests

Integration tests live under `tests/integration/` and are marked with `@pytest.mark.integration`. Run them individually per database:

```bash
make test-duckdb      # no credentials needed
make test-bigquery    # requires BRUIN_TEST_BQ_PROJECT_ID
make test-snowflake   # requires BRUIN_TEST_SF_* env vars
```

**BigQuery** — uses Application Default Credentials by default:

```bash
BRUIN_TEST_BQ_PROJECT_ID=your-project make test-bigquery

# or with a service account:
BRUIN_TEST_BQ_PROJECT_ID=your-project \
BRUIN_TEST_BQ_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}' \
make test-bigquery
```

**Snowflake**:

```bash
BRUIN_TEST_SF_ACCOUNT=xy12345.us-east-1 \
BRUIN_TEST_SF_USERNAME=user \
BRUIN_TEST_SF_PASSWORD=pass \
BRUIN_TEST_SF_DATABASE=mydb \
BRUIN_TEST_SF_WAREHOUSE=mywh \
make test-snowflake
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
