import json
import os

from bruin.exceptions import (
    ConnectionNotFoundError,
    ConnectionParseError,
    ConnectionTypeError,
)


class Connection:
    """A Bruin-managed database connection with lazy client initialization."""

    def __init__(self, name: str, conn_type: str, raw):
        self.name = name
        self.type = conn_type
        self.raw = raw
        self._client = None

    @property
    def client(self):
        if self.type == "generic":
            raise ConnectionTypeError(
                f"Connection '{self.name}' is a generic connection and has no database client. "
                f"Access the raw value with get_connection('{self.name}').raw instead."
            )
        if self._client is None:
            self._client = _create_client(self.type, self.raw)
        return self._client

    def query(self, sql: str) -> "pd.DataFrame | None":
        """Execute *sql* on this connection.

        Returns a pandas DataFrame for data-returning statements,
        or None for DDL/DML.
        """
        from bruin._query import _annotate_sql, _execute

        if self.type == "generic":
            raise ConnectionTypeError(
                f"Cannot run queries against generic connection '{self.name}'."
            )

        annotated = _annotate_sql(sql)
        try:
            return _execute(self, annotated)
        except ConnectionTypeError:
            raise
        except Exception as exc:
            from bruin.exceptions import QueryError
            raise QueryError(
                f"Query failed on connection '{self.name}' ({self.type}): {exc}"
            ) from exc


class GCPConnection(Connection):
    """Google Cloud Platform connection that provides access to multiple GCP services."""

    def __init__(self, name: str, raw: dict):
        super().__init__(name, "google_cloud_platform", raw)
        self._credentials = None
        self._bigquery_client = None

    def _parse_sa_info(self):
        """Parse the service account JSON from the connection payload."""
        try:
            sa_json = self.raw["service_account_json"]
        except KeyError:
            raise ConnectionParseError(
                f"Connection '{self.name}' is missing 'service_account_json' field."
            )
        try:
            return json.loads(sa_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConnectionParseError(
                f"Failed to parse service_account_json for '{self.name}': {exc}"
            ) from exc

    @property
    def credentials(self):
        """Return google.oauth2 credentials from the service account JSON."""
        if self._credentials is None:
            try:
                from google.oauth2 import service_account
            except ImportError:
                raise ImportError(
                    "Install bruin-sdk[bigquery] to use GCP credentials: "
                    "pip install 'bruin-sdk[bigquery]'"
                )
            sa_info = self._parse_sa_info()
            self._credentials = service_account.Credentials.from_service_account_info(sa_info)
        return self._credentials

    def bigquery(self):
        """Return a google.cloud.bigquery.Client."""
        if self._bigquery_client is None:
            try:
                from google.cloud import bigquery
            except ImportError:
                raise ImportError(
                    "Install bruin-sdk[bigquery] to use BigQuery connections: "
                    "pip install 'bruin-sdk[bigquery]'"
                )
            self._bigquery_client = bigquery.Client(
                credentials=self.credentials,
                project=self.raw.get("project_id"),
            )
        return self._bigquery_client

    def sheets(self):
        """Return an authorized pygsheets client."""
        try:
            import pygsheets
        except ImportError:
            raise ImportError(
                "Install bruin-sdk[sheets] to use Google Sheets connections: "
                "pip install 'bruin-sdk[sheets]'"
            )
        return pygsheets.authorize(custom_credentials=self.credentials)

    def storage(self):
        """Return a google.cloud.storage.Client."""
        try:
            from google.cloud import storage
        except ImportError:
            raise ImportError(
                "Install google-cloud-storage to use GCS connections: "
                "pip install google-cloud-storage"
            )
        return storage.Client(
            credentials=self.credentials,
            project=self.raw.get("project_id"),
        )

    @property
    def client(self):
        """Alias for bigquery() — the most common use case."""
        return self.bigquery()


def _create_client(conn_type: str, raw):
    """Create a database client based on connection type."""
    factories = {
        "snowflake": _create_snowflake,
        "postgres": _create_postgres,
        "redshift": _create_postgres,
        "mssql": _create_mssql,
        "mysql": _create_mysql,
        "duckdb": _create_duckdb,
    }
    factory = factories.get(conn_type)
    if factory is None:
        raise ConnectionTypeError(
            f"Unsupported connection type '{conn_type}'. "
            f"Supported types: google_cloud_platform, {', '.join(sorted(factories))}."
        )
    return factory(raw)


def _create_snowflake(raw: dict):
    try:
        import snowflake.connector
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[snowflake] to use Snowflake connections: "
            "pip install 'bruin-sdk[snowflake]'"
        )
    return snowflake.connector.connect(
        account=raw["account"],
        user=raw["username"],
        password=raw["password"],
        database=raw.get("database", ""),
        warehouse=raw.get("warehouse", ""),
        schema=raw.get("schema", ""),
        role=raw.get("role", ""),
    )


def _create_postgres(raw: dict):
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[postgres] to use Postgres/Redshift connections: "
            "pip install 'bruin-sdk[postgres]'"
        )
    return psycopg2.connect(
        host=raw["host"],
        port=raw.get("port", 5432),
        dbname=raw.get("database", ""),
        user=raw["username"],
        password=raw["password"],
        sslmode=raw.get("ssl_mode", "disable"),
    )


def _create_mssql(raw: dict):
    try:
        import pymssql
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[mssql] to use MSSQL connections: "
            "pip install 'bruin-sdk[mssql]'"
        )
    return pymssql.connect(
        server=raw["host"],
        port=raw.get("port", 1433),
        user=raw["username"],
        password=raw["password"],
        database=raw.get("database", ""),
    )


def _create_mysql(raw: dict):
    try:
        import mysql.connector
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[mysql] to use MySQL connections: "
            "pip install 'bruin-sdk[mysql]'"
        )
    return mysql.connector.connect(
        host=raw["host"],
        port=raw.get("port", 3306),
        user=raw["username"],
        password=raw["password"],
        database=raw.get("database", ""),
    )


def _create_duckdb(raw: dict):
    try:
        import duckdb
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[duckdb] to use DuckDB connections: "
            "pip install 'bruin-sdk[duckdb]'"
        )
    return duckdb.connect(raw.get("path", ":memory:"))


def get_connection(name: str) -> "Connection | GCPConnection":
    """Look up a Bruin-managed connection by name and return a Connection object.

    The connection type is resolved from the ``BRUIN_CONNECTION_TYPES`` env var,
    and the connection payload is read from ``os.environ[name]``.
    """
    types_raw = os.environ.get("BRUIN_CONNECTION_TYPES")
    if types_raw is None:
        raise ConnectionNotFoundError(
            f"BRUIN_CONNECTION_TYPES env var is not set. "
            f"Are you running inside 'bruin run'?"
        )

    try:
        type_map = json.loads(types_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ConnectionParseError(
            f"Failed to parse BRUIN_CONNECTION_TYPES: {exc}"
        ) from exc

    conn_type = type_map.get(name)
    if conn_type is None:
        raise ConnectionNotFoundError(
            f"Connection '{name}' not found. "
            f"Available connections: {', '.join(sorted(type_map)) or '(none)'}."
        )

    raw_value = os.environ.get(name)
    if raw_value is None:
        raise ConnectionNotFoundError(
            f"Connection '{name}' is declared in BRUIN_CONNECTION_TYPES but "
            f"its env var is not set."
        )

    if conn_type == "generic":
        raw = raw_value
    else:
        try:
            raw = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConnectionParseError(
                f"Failed to parse connection JSON for '{name}': {exc}"
            ) from exc

    if conn_type == "google_cloud_platform":
        return GCPConnection(name, raw)

    return Connection(name, conn_type, raw)
