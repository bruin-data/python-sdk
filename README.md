# Bruin Python SDK

The official Python SDK for [Bruin CLI](https://github.com/bruin-data/bruin). Query databases, access connections, and read pipeline context — all with zero boilerplate.

```python
from bruin import query, get_connection, context

# One-liner: query any database Bruin manages
df = query("SELECT * FROM users WHERE created_at > '{{start_date}}'")

# Access pipeline context
print(context.start_date)    # datetime.date(2024, 6, 1)
print(context.pipeline)      # "my_pipeline"
print(context.asset_name)    # "my_asset"

# Get a typed database client
conn = get_connection("my_bigquery")
client = conn.client  # google.cloud.bigquery.Client, ready to use
```

## Installation

Add `bruin-sdk` to the `requirements.txt` that sits next to your Python assets:

```
bruin-sdk
pandas
```

For specific database connections, install the corresponding extras:

```
bruin-sdk[bigquery]     # Google BigQuery
bruin-sdk[snowflake]    # Snowflake
bruin-sdk[postgres]     # PostgreSQL / Redshift
bruin-sdk[redshift]     # Redshift (alias for postgres extra)
bruin-sdk[mssql]        # Microsoft SQL Server
bruin-sdk[fabric]       # Microsoft Fabric Warehouse
bruin-sdk[mysql]        # MySQL
bruin-sdk[duckdb]       # DuckDB
bruin-sdk[sheets]       # Google Sheets (for GCP connections)
bruin-sdk[all]          # Everything
```

## Quick Start

### Before (manual boilerplate)

```python
""" @bruin
name: my_asset
connection: bigquery_conn
secrets:
    - key: bigquery_conn
@bruin """

import os
import json
from google.cloud import bigquery

# Parse connection JSON from env var
raw = json.loads(os.environ["bigquery_conn"])
sa_info = json.loads(raw["service_account_json"])

# Create client manually
client = bigquery.Client.from_service_account_info(
    sa_info, project=raw["project_id"]
)

# Execute query
start = os.environ["BRUIN_START_DATE"]
df = client.query(f"SELECT * FROM users WHERE dt >= '{start}'").to_dataframe()
```

### After (with SDK)

```python
""" @bruin
name: my_asset
connection: bigquery_conn
@bruin """

from bruin import query, context

df = query(f"SELECT * FROM users WHERE dt >= '{context.start_date}'")
```

---

## API Reference

### `context`

A module-level object that provides access to all `BRUIN_*` environment variables as properly typed Python values. Each property reads the env var fresh on every access — no caching, no stale values.

```python
from bruin import context
```

| Property | Type | Env Var | Description |
|----------|------|---------|-------------|
| `context.start_date` | `date \| None` | `BRUIN_START_DATE` | Pipeline run start date |
| `context.start_datetime` | `datetime \| None` | `BRUIN_START_DATETIME` | Start date with time |
| `context.start_timestamp` | `datetime \| None` | `BRUIN_START_TIMESTAMP` | Start timestamp with timezone |
| `context.end_date` | `date \| None` | `BRUIN_END_DATE` | Pipeline run end date |
| `context.end_datetime` | `datetime \| None` | `BRUIN_END_DATETIME` | End date with time |
| `context.end_timestamp` | `datetime \| None` | `BRUIN_END_TIMESTAMP` | End timestamp with timezone |
| `context.execution_date` | `date \| None` | `BRUIN_EXECUTION_DATE` | Execution date |
| `context.execution_datetime` | `datetime \| None` | `BRUIN_EXECUTION_DATETIME` | Execution date with time |
| `context.execution_timestamp` | `datetime \| None` | `BRUIN_EXECUTION_TIMESTAMP` | Execution timestamp with timezone |
| `context.run_id` | `str \| None` | `BRUIN_RUN_ID` | Unique run identifier |
| `context.pipeline` | `str \| None` | `BRUIN_PIPELINE` | Pipeline name |
| `context.asset_name` | `str \| None` | `BRUIN_ASSET` | Current asset name |
| `context.connection` | `str \| None` | `BRUIN_CONNECTION` | Asset's default connection |
| `context.is_full_refresh` | `bool` | `BRUIN_FULL_REFRESH` | `True` when `--full-refresh` flag is set |
| `context.commit_hash` | `str \| None` | `BRUIN_COMMIT_HASH` | Git commit hash of the pipeline's repository |
| `context.vars` | `dict` | `BRUIN_VARS` | Pipeline variables (types preserved from JSON Schema) |

All properties return `None` when the corresponding env var is missing (except `is_full_refresh` which returns `False`, and `vars` which returns `{}`).

```python
from bruin import context

# Dates
print(context.start_date)       # datetime.date(2024, 6, 1)
print(context.end_date)         # datetime.date(2024, 6, 2)

# Pipeline variables (types preserved from pipeline.yml JSON Schema)
segment = context.vars["segment"]     # str: "enterprise"
horizon = context.vars["horizon"]     # int: 30
cohorts = context.vars["cohorts"]     # list[dict]

# Conditional logic
if context.is_full_refresh:
    df = query("SELECT * FROM users")
else:
    df = query(f"SELECT * FROM users WHERE dt >= '{context.start_date}'")
```

---

### `query(sql, connection=None)`

Render SQL with the Bruin CLI (Jinja templates and environment schema prefixes),
then execute the rendered SQL with the existing Python database client and return results.

```python
from bruin import query
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sql` | `str` | *(required)* | SQL statement to execute |
| `connection` | `str \| None` | `None` | Connection name. When `None`, uses the asset's default connection (`BRUIN_CONNECTION`) |

**Returns:** `pandas.DataFrame` for data-returning statements (`SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`), `None` for DDL/DML (`CREATE`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc.).

```python
# Uses the asset's default connection (from the `connection:` field in asset definition)
df = query("SELECT * FROM users")

# Explicit connection name
df = query("SELECT * FROM users", connection="my_bigquery")

# DDL/DML returns None
query("CREATE TABLE temp_users AS SELECT * FROM users")
query("INSERT INTO audit_log VALUES ('ran_asset', NOW())")

# Works with any supported database
df_bq = query("SELECT * FROM users", connection="my_bigquery")
df_sf = query("SELECT * FROM users", connection="my_snowflake")
df_pg = query("SELECT * FROM users", connection="my_postgres")
```

Every query is automatically annotated with `@bruin.config` metadata for observability and cost tracking.

#### CLI rendering requirements

Both `query()` and `get_connection(...).query()` render before executing. The selected
connection name is passed to the renderer; execution still uses that connection's
existing Python client and injected credentials. Result handling is unchanged: the
driver supplies the DataFrame or `None` (DuckDB also returns DataFrames for DDL/DML).
The CLI only returns SQL; it never executes the query or transports result data.

```python
df = query("SELECT * FROM analytics.events WHERE dt >= '{{ start_date }}'")
conn = get_connection("my_bigquery")
df = conn.query("SELECT '{{ start_date }}' AS run_start")
```

**Pending CLI integration:** the CLI change is being developed separately. The
following provisional contract must be verified against that implementation before
release; these flags and response format are not claimed to exist in a released CLI:

```text
bruin render --stdin --connection NAME --raw-query --output json
stdin: the query SQL
stdout: {"query": "rendered SQL"}
```

The stdin mode must render only the supplied query, including Jinja and schema
prefixes, without asset materialization or asset hooks. The SDK does not create a
temporary SQL asset. The process inherits the current working directory and a copy
of the full environment, including `BRUIN_CONFIG_FILE`, connection credentials,
`BRUIN_THIS`, asset/pipeline names, execution time, and run ID. Only the child's
`BRUIN_CONNECTION` is overridden with the selected connection name; the parent's
environment and Python connection remain unchanged.

`BRUIN_ENVIRONMENT`, when present, is also passed as `--environment`.
`BRUIN_START_DATETIME` / `BRUIN_END_DATETIME` (falling back to the corresponding
`*_DATE` values) are passed as `--start-date` / `--end-date`.
`BRUIN_FULL_REFRESH=1` adds `--full-refresh`, and typed `context.vars` are passed
as repeated `--var KEY=JSON` arguments. The CLI must honor the inherited run
context in stdin mode. With no run context, CLI defaults apply.

The SDK invokes `bruin` from `PATH`, or the executable specified by `BRUIN_PATH`,
without a shell and sends SQL through stdin. A missing/unusable binary, nonzero
render exit, invalid/empty JSON query, or 60-second render timeout raises
`QueryError` before touching the database client. No original-SQL fallback is used.
Compatibility is based on the command contract, not a guessed minimum version:
older CLIs without this stdin mode fail with an upgrade message. The CLI release
providing this contract must be identified during the pending integration check.
Direct native client calls such as `conn.client.query(...)` bypass SDK rendering.

---

### `get_connection(name)`

Get a typed connection object with a lazy database client.

```python
from bruin import get_connection
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Connection name as defined in `.bruin.yml` (auto-injected from `connection:` or listed in `secrets`) |

**Returns:** `Connection` or `GCPConnection` depending on the connection type.

```python
conn = get_connection("my_bigquery")
conn.name    # "my_bigquery"
conn.type    # "google_cloud_platform"
conn.raw     # dict — the parsed connection JSON
conn.client  # Lazy-initialized database client
```

#### Connection types

| Type | `.client` returns | Install extra |
|------|-------------------|---------------|
| `google_cloud_platform` | `bigquery.Client` | `bruin-sdk[bigquery]` |
| `snowflake` | `snowflake.connector.Connection` | `bruin-sdk[snowflake]` |
| `postgres` | `psycopg2.connection` | `bruin-sdk[postgres]` |
| `redshift` | `psycopg2.connection` | `bruin-sdk[redshift]` |
| `mssql` | `pymssql.Connection` | `bruin-sdk[mssql]` |
| `fabric` | `pyodbc.Connection` or `pymssql.Connection` | `bruin-sdk[fabric]` |
| `mysql` | `mysql.connector.Connection` | `bruin-sdk[mysql]` |
| `duckdb` | `duckdb.DuckDBPyConnection` | `bruin-sdk[duckdb]` |
| `generic` | N/A (raises error) | — |

Client creation is **lazy** — the actual database connection is only established when `.client` is first accessed.

#### Fabric connections

Fabric supports three authentication modes, selected by the fields present on the connection:

| Fields | Mode | Driver |
|--------|------|--------|
| `use_azure_default_credential: true` | `DefaultAzureCredential` (e.g. `az login`, managed identity) | `pyodbc` |
| `client_id` + `client_secret` + `tenant_id` | Microsoft Entra ID service principal | `pyodbc` |
| `username` + `password` | SQL authentication | `pymssql` |

The Microsoft Entra ID modes acquire an access token and hand it to the driver, which requires an
[ODBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
(msodbcsql18 or newer) on the machine running the asset. The newest installed driver is used unless
the connection sets `driver` explicitly.

#### GCP connections

GCP connections have extra methods since one connection can access multiple Google services:

```python
conn = get_connection("my_gcp")

# BigQuery (most common — also available as .client)
bq_client = conn.bigquery()
df = bq_client.query("SELECT 1").to_dataframe()

# Google Sheets
sheets_client = conn.sheets()  # requires bruin-sdk[sheets]

# Cloud Storage
gcs_client = conn.storage()  # requires google-cloud-storage

# Raw credentials for any Google API
creds = conn.credentials  # google.oauth2.Credentials
```

#### Generic connections

Generic connections hold a raw string value (like an API key or webhook URL). They don't have a database client:

```python
conn = get_connection("slack_webhook")
conn.type    # "generic"
conn.raw     # "https://hooks.slack.com/services/T00/B00/xxx"
conn.client  # raises ConnectionTypeError
```

---

### `Connection.query(sql)`

Connections also have a `.query()` method — an alternative to the top-level `query()`:

```python
conn = get_connection("my_bigquery")

# These are equivalent:
df = conn.query("SELECT * FROM users")
df = query("SELECT * FROM users", connection="my_bigquery")
```

Same return behavior: `DataFrame` for SELECT, `None` for DDL/DML.

---

## Exceptions

All SDK exceptions inherit from `BruinError`:

```python
from bruin.exceptions import (
    BruinError,              # Base class
    ConnectionNotFoundError, # Connection name not found or env var missing
    ConnectionParseError,    # Invalid JSON in connection env var
    ConnectionTypeError,     # Unsupported or generic connection type
    CLIError,               # Bruin CLI process failed
    QueryError,              # SQL rendering or execution failed
)
```

```python
try:
    df = query("SELECT * FROM users", connection="missing")
except ConnectionNotFoundError as e:
    print(e)
    # Connection 'missing' not found. Available connections: my_bigquery, my_snowflake.
```

Missing optional dependencies give clear install instructions:

```python
conn = get_connection("my_snowflake")
conn.client
# ImportError: Install bruin-sdk[snowflake] to use Snowflake connections:
#   pip install 'bruin-sdk[snowflake]'
```

---

## Asset Setup

When you set the `connection` field in your asset definition, Bruin automatically injects the connection's credentials — no need to list it in `secrets`:

```python
""" @bruin
name: my_asset
connection: my_bigquery
@bruin """

from bruin import query

# Uses my_bigquery automatically
df = query("SELECT * FROM users")
```

If you need additional connections beyond the default, add them to `secrets`:

```python
""" @bruin
name: my_asset
connection: my_bigquery
secrets:
    - key: my_postgres
@bruin """

from bruin import query, get_connection

# Default connection (my_bigquery)
df = query("SELECT * FROM users")

# Additional connection via secrets
pg = get_connection("my_postgres")
```

---

## Examples

### Incremental load with date filtering

```python
""" @bruin
name: analytics.daily_events
connection: my_bigquery
@bruin """

from bruin import query, context

if context.is_full_refresh:
    df = query("SELECT * FROM raw.events")
else:
    df = query(f"""
        SELECT * FROM raw.events
        WHERE event_date BETWEEN '{context.start_date}' AND '{context.end_date}'
    """)

print(f"Loaded {len(df)} events")
```

### Cross-database ETL

```python
""" @bruin
name: sync.postgres_to_bigquery
secrets:
    - key: my_postgres
    - key: my_bigquery
@bruin """

from bruin import query, get_connection

# Read from Postgres
df = query("SELECT * FROM users WHERE active = true", connection="my_postgres")

# Write to BigQuery
bq = get_connection("my_bigquery")
df.to_gbq(
    "staging.active_users",
    project_id=bq.raw["project_id"],
    credentials=bq.credentials,
    if_exists="replace",
)
```

### Using pipeline variables

```yaml
# pipeline.yml
name: marketing
variables:
  segment:
    type: string
    default: "enterprise"
  lookback_days:
    type: integer
    default: 30
```

```python
""" @bruin
name: marketing.segment_report
connection: my_snowflake
@bruin """

from bruin import query, context

segment = context.vars["segment"]
lookback = context.vars["lookback_days"]

df = query(f"""
    SELECT * FROM customers
    WHERE segment = '{segment}'
    AND created_at >= DATEADD(day, -{lookback}, CURRENT_DATE())
""")

print(f"Found {len(df)} {segment} customers in last {lookback} days")
```

### DDL operations

```python
""" @bruin
name: setup.create_tables
connection: my_postgres
@bruin """

from bruin import query

# DDL returns None
query("CREATE TABLE IF NOT EXISTS audit_log (event TEXT, ts TIMESTAMP)")
query("INSERT INTO audit_log VALUES ('setup_complete', NOW())")

# SELECT returns DataFrame
df = query("SELECT COUNT(*) as cnt FROM audit_log")
print(f"Audit log has {df['cnt'][0]} entries")
```

## Disclaimer

This project is written entirely by machines.

Not a single line of code in this repository was authored by a human. Every function, module, and commit is generated by AI. We intend to keep it that way.

The engineering team at [Bruin](https://getbruin.com) does not write the code. We guide the machines that do.
