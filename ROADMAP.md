# Bruin Python Package — Roadmap

## Environment Handling

Environments are **automatic**. When Bruin runs a Python asset (`bruin run --environment production`), it resolves the correct connections for that environment and injects them as env vars before your code executes. By the time Python runs, the environment is already decided.

The package just uses what Bruin gives it. No environment parameter needed in Python code.

For CLI wrappers (v0.3) that call `bruin` commands directly, environment is passed through to the CLI — but that's the only place it appears.

---

## v0.1 — Core (The Foundation)

The things every Bruin Python asset needs. This alone eliminates 80% of helpers.py boilerplate.

### Query

The killer feature. One function, any database, returns a DataFrame.

```python
from bruin import query

df = query("SELECT * FROM users", connection="my_bigquery")
df = query("SELECT * FROM orders WHERE date > :start", connection="snowflake_prod", start_date="2024-01-01")
```

- Wraps `bruin query --output json` under the hood
- Returns pandas DataFrame
- Supports all Bruin-supported platforms (BigQuery, Snowflake, Postgres, Redshift, Athena, DuckDB, Databricks, MSSQL, etc.)
- Passes through `limit`, `timeout`, `start_date`, `end_date`

### Bruin Context

Every Python asset reads env vars for dates and variables. Make it Pythonic.

```python
from bruin import context

context.start_date        # datetime.date(2024, 1, 15)
context.end_date          # datetime.date(2024, 1, 16)
context.start_datetime    # datetime.datetime(2024, 1, 15, 13, 45, 30)
context.execution_date    # datetime.date(2024, 1, 15)
context.run_id            # "abc-123"
context.pipeline          # "my_pipeline"
context.asset_name        # "tier1.my_asset"
context.is_full_refresh   # False
context.vars              # {"segment": "enterprise", "horizon": 30}
context.vars["segment"]   # "enterprise"
```

- Parses BRUIN_* env vars into proper Python types
- `start_date`/`end_date` → `datetime.date`
- `start_datetime` → `datetime.datetime`
- `vars` → dict (parsed from BRUIN_VARS JSON)
- `is_full_refresh` → bool
- Graceful behavior when running outside `bruin run` (returns None or sensible defaults)

### Native Client Access

For when you need more than a query (uploads, DDL, API calls).

```python
from bruin import get_connection

bq = get_connection("my_bigquery").client        # google.cloud.bigquery.Client
sf = get_connection("my_snowflake").client        # snowflake.connector.Connection
pg = get_connection("my_postgres").client         # psycopg2 connection
creds = get_connection("my_gcp").credentials      # google.oauth2.Credentials
```

- Parses Bruin's injected env var JSON automatically
- Detects connection type and creates the right client
- Supports: BigQuery, Snowflake, Postgres, MSSQL, AWS (boto3), GCP credentials
- Lazy initialization (client created on first access)

---

## v0.2 — Common Operations

The most-repeated patterns from real-world Bruin projects.

### Slack

```python
from bruin import slack

slack.send("slack_webhook", "Deployment complete")
slack.send("slack_webhook", "Pipeline failed!", channel="#alerts")  # if API token
```

### Google Sheets

```python
from bruin import gsheets

# Read
df = gsheets.read("gcp_conn", spreadsheet_id="...", sheet="Sheet1")

# Write (clear + upload)
gsheets.write(df, "gcp_conn", spreadsheet_id="...", sheet="Sheet1")

# Append
gsheets.append(df, "gcp_conn", spreadsheet_id="...", sheet="Sheet1")

# Update a cell
gsheets.update_cell("gcp_conn", spreadsheet_id="...", sheet="Sheet1", cell="A1", value="hello")
```

### DataFrame to Table

For writing data back to warehouses without materialization config.

```python
from bruin import write

write(df, "my_bigquery", table="schema.table_name", mode="replace")  # or "append", "merge"
```

---

## v0.3 — CLI Wrappers

For building tools, automations, and CI/CD integrations on top of Bruin.

### Pipeline Operations

```python
from bruin import pipeline

# Run
result = pipeline.run("path/to/pipeline", environment="production")

# Validate
issues = pipeline.validate("path/to/pipeline")

# Render SQL with variables
sql = pipeline.render("path/to/asset.sql", start_date="2024-01-01")

# Get lineage
lineage = pipeline.lineage("path/to/asset.sql")
```

### Connection Management

```python
from bruin import connections

# List all connections
conns = connections.list()

# Test a connection
ok = connections.test("my_bigquery")
```

---

## v0.4 — Developer Experience

### Local Mode

Auto-detect whether running inside `bruin run` (env vars) or standalone (read `.bruin.yml`).

```python
from bruin import query

# Inside bruin run: uses injected env vars
# Standalone: reads .bruin.yml from project root
df = query("SELECT 1", connection="my_bigquery")
```

### Mock Connections for Testing

```python
from bruin.testing import mock_connection, mock_context
import pandas as pd

# Mock a query response
with mock_connection("my_bigquery", query_results=pd.DataFrame({"id": [1, 2]})):
    result = query("SELECT * FROM users", connection="my_bigquery")
    assert len(result) == 2

# Mock Bruin context
with mock_context(start_date="2024-01-01", pipeline="test"):
    assert context.start_date == date(2024, 1, 1)
```

### Error Messages

Clear messages when things go wrong:

```
bruin.ConnectionNotFoundError: Connection "my_bigqurey" not found.
  Available connections: my_bigquery, snowflake_prod, postgres_dev
  Did you mean "my_bigquery"?

bruin.BruinCLINotFoundError: Bruin CLI not found.
  Install it with: curl -sSL https://raw.githubusercontent.com/bruin-data/bruin/main/install.sh | bash
```

---

## Future — Community Driven

These are too specific for the core package. Could be separate packages or added based on demand.

- **API integrations** (Meta Ads, AppsFlyer, etc.) → too client-specific
- **Email notifications** via SMTP
- **Google Drive** upload/download
- **S3 read/write** (DataFrame ↔ S3)
- **Generic REST API** helper with Bruin connection auth
- **Asset scaffolding** (generate Python asset boilerplate from templates)
