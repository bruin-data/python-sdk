# Bruin Python SDK — Product Requirements Document

## Overview

A Python package that eliminates boilerplate in Bruin Python assets. Instead of manually parsing credentials, creating database clients, and writing repetitive helper functions, users install one package and get instant access to their Bruin-managed connections.

**Package name:** `bruin-sdk` (on PyPI)
**Import name:** `bruin`

## Problem

Bruin manages connections and credentials centrally via `.bruin.yml`. When running Python assets, it injects these connections as JSON-serialized environment variables. However, every Python asset must manually:

1. Parse the JSON from environment variables
2. For GCP: double-deserialize (`json.loads` twice — once for the env var, once for the nested `service_account_json`)
3. Import platform-specific libraries (google.cloud.bigquery, snowflake.connector, etc.)
4. Construct native clients from the parsed credentials
5. Execute queries and handle results

This leads to a `helpers.py` file being copy-pasted into every project. Analysis of 12 real-world Bruin projects revealed:

- The same `get_bq_client()` function copied verbatim in 8+ projects
- The same `send_slack_message()` function in 5 projects
- Google Sheets upload logic duplicated across 3 projects (one project had 8 variants totaling 268 lines)
- AWS credential extraction repeated 3 times within a single project
- Zero code reuse between projects

Every new project starts by copying helpers.py from a previous one and modifying it. This is error-prone, inconsistent, and wastes time.

## Solution

A pip-installable package that provides:

1. **One-line queries** against any Bruin-managed connection, returning a pandas DataFrame
2. **Automatic credential parsing** from Bruin's injected environment variables
3. **Native client access** for platform-specific operations (uploads, DDL, etc.)
4. **Pythonic access** to Bruin runtime context (dates, variables, run metadata)
5. **Common operation helpers** for Slack, Google Sheets, and data writing

## How It Works

Bruin handles environments and credential injection before Python code runs:

```
bruin run --environment production
  └─ resolves connections from .bruin.yml for "production"
  └─ serializes them as JSON into environment variables
  └─ executes the Python asset
       └─ bruin-sdk reads env vars, creates clients, runs queries
```

The package never deals with environments directly. By the time Python executes, the right credentials are already available as env vars. The package simply makes them easy to use.

## Target Users

1. **Data engineers** writing Bruin Python assets who query databases, call APIs, and load data
2. **Analytics engineers** who need to fetch data from warehouses in Python scripts
3. **Anyone using Bruin** who writes Python assets and is tired of boilerplate

## Requirements

### v0.1 — Core

The foundation that eliminates 80% of existing helpers.py boilerplate.

#### R1: Query

Execute SQL against any Bruin-managed connection, return a pandas DataFrame.

```python
from bruin import query

df = query("SELECT * FROM users", connection="my_bigquery")
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| sql | str | yes | SQL query to execute |
| connection | str | yes | Connection name as defined in .bruin.yml |

Implementation: uses `get_connection()` (R3) to obtain the native client, executes the query using the platform's Python library, and returns a pandas DataFrame. No Bruin CLI dependency.

Each platform uses its native method to return a DataFrame:

| Platform | Library | Execution Method |
|----------|---------|------------------|
| BigQuery | google-cloud-bigquery | `client.query(sql).to_dataframe()` |
| Snowflake | snowflake-connector-python | `cursor.execute(sql).fetch_pandas_all()` |
| Postgres | psycopg2 + pandas | `pd.read_sql(sql, conn)` |
| MSSQL | pymssql + pandas | `pd.read_sql(sql, conn)` |
| MySQL | mysql-connector-python + pandas | `pd.read_sql(sql, conn)` |
| Redshift | psycopg2 + pandas | `pd.read_sql(sql, conn)` |
| DuckDB | duckdb | `conn.execute(sql).fetchdf()` |
| Databricks | databricks-sql-connector | `pd.read_sql(sql, conn)` |

#### R2: Bruin Context

Parse Bruin's runtime environment variables into proper Python types.

```python
from bruin import context

context.start_date        # datetime.date
context.end_date          # datetime.date
context.start_datetime    # datetime.datetime
context.end_datetime      # datetime.datetime
context.execution_date    # datetime.date
context.run_id            # str
context.pipeline          # str
context.asset_name        # str
context.is_full_refresh   # bool
context.vars              # dict (types preserved from JSON Schema)
context.vars["segment"]   # str — "enterprise"
context.vars["horizon"]   # int — 30
context.vars["cohorts"]   # list[dict] — [{"name": "baseline", "weight": 0.6}, ...]
```

Pipeline variables are defined with JSON Schema types in `pipeline.yml`. `BRUIN_VARS` is a JSON string that preserves these types. The package parses it once via `json.loads`, so values come back as their true Python types — not strings:

| JSON Schema Type | Python Type | Example |
|------------------|-------------|---------|
| string | str | `"enterprise"` |
| integer | int | `30` |
| number | float | `0.6` |
| boolean | bool | `True` |
| array | list | `[{"name": "a"}, {"name": "b"}]` |
| object | dict | `{"name": "baseline", "weight": 0.6}` |

Source environment variables:

| Property | Env Var | Python Type |
|----------|---------|-------------|
| start_date | BRUIN_START_DATE | datetime.date |
| end_date | BRUIN_END_DATE | datetime.date |
| start_datetime | BRUIN_START_DATETIME | datetime.datetime |
| end_datetime | BRUIN_END_DATETIME | datetime.datetime |
| execution_date | BRUIN_EXECUTION_DATE | datetime.date |
| run_id | BRUIN_RUN_ID | str |
| pipeline | BRUIN_PIPELINE | str |
| asset_name | BRUIN_THIS | str |
| is_full_refresh | BRUIN_FULL_REFRESH | bool |
| vars | BRUIN_VARS | dict (JSON-parsed, types preserved) |

When running outside of `bruin run` (e.g., local development), properties return `None` rather than raising errors.

#### R3: Native Client Access

Parse Bruin's injected connection env vars and return platform-native clients.

```python
from bruin import get_connection

conn = get_connection("my_bigquery")
conn.client       # google.cloud.bigquery.Client
conn.credentials  # google.oauth2.Credentials
conn.raw          # dict — the raw parsed JSON from env var
```

Supported connection types and what `.client` returns:

| Connection Type | `.client` Returns | Required Extras |
|-----------------|-------------------|-----------------|
| google_cloud_platform | google.cloud.bigquery.Client | `google-cloud-bigquery` |
| snowflake | snowflake.connector.Connection | `snowflake-connector-python` |
| postgres | psycopg2.connection | `psycopg2-binary` |
| mssql | pymssql.Connection | `pymssql` |
| mysql | mysql.connector.Connection | `mysql-connector-python` |
| aws | boto3.Session | `boto3` |

Platform-specific client libraries are optional dependencies (extras). The core package has no heavy dependencies.

Client creation is lazy — the client is only instantiated when `.client` is first accessed.

### v0.2 — Common Operations

Helpers for the most-repeated patterns across Bruin projects.

#### R4: Slack Notifications

```python
from bruin import slack

slack.send("slack_webhook_conn", "Deployment complete")
```

Supports both webhook URLs and Slack API tokens. Parses the connection format automatically.

#### R5: Google Sheets

```python
from bruin import gsheets

df = gsheets.read("gcp_conn", spreadsheet_id="...", sheet="Sheet1")
gsheets.write(df, "gcp_conn", spreadsheet_id="...", sheet="Sheet1")
gsheets.append(df, "gcp_conn", spreadsheet_id="...", sheet="Sheet1")
gsheets.update_cell("gcp_conn", spreadsheet_id="...", sheet="Sheet1", cell="A1", value="hello")
```

Uses the GCP connection's service account credentials with Sheets API scopes. Replaces 8+ functions typically found in helpers.py with 4 clean methods.

#### R6: DataFrame to Table

```python
from bruin import write

write(df, "my_bigquery", table="schema.table_name", mode="replace")
```

Modes: `replace`, `append`, `merge`. Uses the native client from R3 to upload data.

### v0.3 — Developer Experience

#### R7: Local Mode

Auto-detect whether running inside `bruin run` (env vars present) or standalone (read `.bruin.yml` from project root). The user's code stays the same in both cases.

#### R8: Mock Connections for Testing

```python
from bruin.testing import mock_connection, mock_context

with mock_connection("my_bigquery", query_results=pd.DataFrame({"id": [1, 2]})):
    result = query("SELECT * FROM users", connection="my_bigquery")
    assert len(result) == 2

with mock_context(start_date="2024-01-01", pipeline="test"):
    assert context.start_date == date(2024, 1, 1)
```

#### R9: Error Messages

Friendly, actionable error messages:

```
bruin.ConnectionNotFoundError: Connection "my_bigqurey" not found.
  Available connections: my_bigquery, snowflake_prod, postgres_dev
  Did you mean "my_bigquery"?

bruin.BruinCLINotFoundError: Bruin CLI not found.
  Install it with: curl -sSL https://raw.githubusercontent.com/bruin-data/bruin/main/install.sh | bash
```

## Non-Goals

The following are explicitly out of scope:

- **API-specific integrations** (Meta Ads, AppsFlyer, etc.) — too client-specific for a general package
- **CLI wrappers** (pipeline.run, validate, render, lineage) — users can call `bruin` directly from the terminal or CI/CD
- **Managing .bruin.yml** — the package reads connections, it doesn't manage them
- **Environment resolution** — Bruin handles this before Python runs
- **Custom asset runners** — Bruin's asset execution is handled by the CLI

## Package Structure

```
bruin-sdk/
  pyproject.toml
  src/
    bruin/
      __init__.py          # query(), get_connection(), context
      _query.py            # query execution via native clients
      _context.py          # BRUIN_* env var parsing
      _connection.py       # connection parsing + native client creation
      slack.py             # slack.send()
      gsheets.py           # gsheets.read(), write(), append(), update_cell()
      testing.py           # mock_connection(), mock_context()
      exceptions.py        # ConnectionNotFoundError, BruinCLINotFoundError, etc.
```

## Dependencies

### Core (v0.1)
- `pandas` — DataFrame return type for query()
- No other required dependencies

### Optional Extras
- `bruin-sdk[bigquery]` → `google-cloud-bigquery`, `google-auth`
- `bruin-sdk[snowflake]` → `snowflake-connector-python`
- `bruin-sdk[postgres]` → `psycopg2-binary`
- `bruin-sdk[mssql]` → `pymssql`
- `bruin-sdk[mysql]` → `mysql-connector-python`
- `bruin-sdk[aws]` → `boto3`
- `bruin-sdk[sheets]` → `pygsheets`, `google-auth`
- `bruin-sdk[slack]` → `requests`
- `bruin-sdk[all]` → everything above

### System Requirement
- Bruin CLI is NOT required. The package uses native Python libraries directly.

## Success Metrics

1. **Adoption**: new Bruin projects stop creating helpers.py files
2. **Reduction**: average Python asset code drops by 50%+ lines
3. **Time to first query**: from "create project" to "DataFrame in hand" under 2 minutes
4. **Zero-config**: works immediately with existing .bruin.yml — no additional setup

## Future — Caching

Two problems caching solves:

1. **Iteration speed**: ML and ingestion development means running the same code over and over while tweaking transformations. Re-fetching the same dataset or API response every time is slow and wasteful.
2. **Rate limits**: APIs (Facebook, Shopify, AppsFlyer, etc.) have strict rate limits. Hitting the same endpoint repeatedly during development burns through quotas. One bad debugging session can exhaust a daily limit.

Caching eliminates both: fetch once, iterate locally as many times as you need.

```python
from bruin import query

# First call: hits BigQuery, caches result locally
df = query("SELECT * FROM events", connection="my_bigquery", cache=True)

# Second call: same SQL + same connection = instant, loaded from local cache
df = query("SELECT * FROM events", connection="my_bigquery", cache=True)

# Force refresh when the underlying data has changed
df = query("SELECT * FROM events", connection="my_bigquery", cache=True, refresh=True)

# Cache with a TTL — auto-refresh after expiry
df = query("SELECT * FROM events", connection="my_bigquery", cache="1h")
```

How it works:
- Cache key = hash of (SQL string + connection name)
- Cached as local Parquet files (fast reads, preserves types, compact on disk)
- Stored in `.bruin/cache/` in the project directory
- `cache=True` caches indefinitely until manually refreshed
- `cache="1h"` / `cache="30m"` / `cache="1d"` sets a TTL
- `refresh=True` forces a fresh query and updates the cache
- Cache is local and gitignored — never committed

This same caching layer could later extend to API requests and any expensive computation. Three API caching approaches to consider:

### Option A: Decorator

```python
from bruin import cache

@cache(ttl="1h")
def fetch_campaigns(account_id, start_date):
    # expensive API calls, pagination, rate limiting, etc.
    return df

# First call: hits API, caches result
df = fetch_campaigns("acc123", "2024-01-01")

# Second call: same args = instant from cache
df = fetch_campaigns("acc123", "2024-01-01")

# Different args = new API call, cached separately
df = fetch_campaigns("acc456", "2024-01-01")
```

Cache key = hash of (function name + args + kwargs). Clean and Pythonic. Downside: everything must be wrapped in a function.

### Option B: Context Manager

```python
from bruin import cache

with cache("campaign_data", ttl="1h") as c:
    df = fetch_from_api(...)
    c.set(df)

# Later
with cache("campaign_data") as c:
    df = c.get()  # from cache if available
```

Explicit control over what gets cached. Downside: verbose, manual save/load logic.

### Option C: Explicit Get/Set

```python
from bruin import cache

df = cache.get("campaign_data")
if df is None:
    df = fetch_from_api(...)
    cache.set("campaign_data", df, ttl="1h")
```

Full control, no magic. Downside: boilerplate on every call site.

### Hybrid: Decorator + Inline Call

Combine the best of A and C — `cache` works both as a decorator and as a direct call:

```python
from bruin import cache

# As decorator — for reusable functions
@cache(ttl="1h")
def fetch_campaigns(account_id, start_date):
    return expensive_api_call(...)

df = fetch_campaigns("acc123", "2024-01-01")

# As inline call — for one-off stuff, no function needed
df = cache(lambda: requests.get("https://api.example.com/data").json(), key="api_data", ttl="1h")
```

Decorator form auto-derives the cache key from function name + args. Inline form requires an explicit `key`.

**Decision deferred** — to be revisited when we get to this stage.

## Release Plan

| Version | Scope | Requirements |
|---------|-------|--------------|
| v0.1 | Core: query, context, native clients | R1, R2, R3 |
| v0.2 | Common operations: Slack, Sheets, write | R4, R5, R6 |
| v0.3 | DX: local mode, testing, error messages | R7, R8, R9 |
| Future | Query caching for fast ML iteration | See above |
