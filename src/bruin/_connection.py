import json
import logging
import os

from bruin.exceptions import (
    ConnectionNotFoundError,
    ConnectionParseError,
    ConnectionTypeError,
)

logger = logging.getLogger("bruin")


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
            logger.debug("Creating %s client for connection '%s'", self.type, self.name)
            self._client = _create_client(self.type, self.raw)
        return self._client

    def query(self, sql: str) -> "pd.DataFrame | None":
        """Execute *sql* on this connection.

        Returns a pandas DataFrame for data-returning statements,
        or None for DDL/DML.
        """
        from bruin._query import _run_query

        return _run_query(self, sql)

    def close(self):
        """Close the underlying database client if it was initialized."""
        if self._client is None:
            return
        logger.debug("Closing client for connection '%s'", self.name)
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._client = None

    def __repr__(self):
        return f"Connection(name={self.name!r}, type={self.type!r})"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class GCPConnection(Connection):
    """Google Cloud Platform connection that provides access to multiple GCP services."""

    def __init__(self, name: str, raw: dict):
        super().__init__(name, "google_cloud_platform", raw)
        self._credentials = None
        self._bigquery_client = None
        self._sheets_client = None

    def _uses_adc(self) -> bool:
        """Return True when the connection is configured for Application Default Credentials."""
        return self.raw.get("use_application_default_credentials") in ("true", "True", True)

    def _parse_sa_info(self):
        """Parse the service account JSON from the connection payload."""
        sa_json = self.raw.get("service_account_json", "")
        if not sa_json:
            return None
        try:
            return json.loads(sa_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConnectionParseError(
                f"Failed to parse service_account_json for '{self.name}': {exc}"
            ) from exc

    @property
    def credentials(self):
        """Return google credentials.

        Supports three modes (checked in order):
        1. Inline service-account JSON (``service_account_json``)
        2. Application Default Credentials (``use_application_default_credentials``)
        3. Fallback to ADC when neither is provided
        """
        if self._credentials is not None:
            return self._credentials

        sa_info = self._parse_sa_info()

        if sa_info is not None and not self._uses_adc():
            try:
                from google.oauth2 import service_account
            except ImportError:
                raise ImportError(
                    "Install bruin-sdk[bigquery] to use GCP credentials: "
                    "pip install 'bruin-sdk[bigquery]'"
                )
            logger.debug("Using service account credentials for '%s'", self.name)
            self._credentials = service_account.Credentials.from_service_account_info(sa_info)
        else:
            try:
                import google.auth
            except ImportError:
                raise ImportError(
                    "Install bruin-sdk[bigquery] to use GCP credentials: "
                    "pip install 'bruin-sdk[bigquery]'"
                )
            logger.debug("Using Application Default Credentials for '%s'", self.name)
            self._credentials, _ = google.auth.default()

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
            logger.debug(
                "Creating BigQuery client for '%s' (project=%s)",
                self.name, self.raw.get("project_id"),
            )
            self._bigquery_client = bigquery.Client(
                credentials=self.credentials,
                project=self.raw.get("project_id"),
            )
        return self._bigquery_client

    def sheets(self):
        """Return a cached, authorized pygsheets client with Sheets + Drive scopes."""
        if self._sheets_client is None:
            try:
                import pygsheets
            except ImportError:
                raise ImportError(
                    "Install bruin-sdk[sheets] to use Google Sheets connections: "
                    "pip install 'bruin-sdk[sheets]'"
                )
            _SHEETS_SCOPES = (
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            )
            scoped = self.credentials.with_scopes(_SHEETS_SCOPES)
            self._sheets_client = pygsheets.authorize(custom_credentials=scoped)
        return self._sheets_client

    def read_sheet(self, spreadsheet, worksheet="Sheet1"):
        """Read a Google Sheets worksheet into a pandas DataFrame."""
        from bruin._sheets import _read_sheet_impl
        return _read_sheet_impl(self, spreadsheet, worksheet)

    def write_sheet(self, df, spreadsheet, worksheet="Sheet1", fit=True):
        """Write a pandas DataFrame to a Google Sheets worksheet."""
        from bruin._sheets import _write_sheet_impl
        _write_sheet_impl(self, df, spreadsheet, worksheet, fit)

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

    def close(self):
        """Close the BigQuery and Sheets clients if initialized."""
        if self._bigquery_client is not None:
            logger.debug("Closing BigQuery client for connection '%s'", self.name)
            close = getattr(self._bigquery_client, "close", None)
            if callable(close):
                close()
            self._bigquery_client = None
        self._sheets_client = None
        self._credentials = None


class GoogleSheetsConnection(Connection):
    """Standalone Google Sheets connection (mirrors Go CLI's ``google_sheets`` type)."""

    def __init__(self, name: str, raw: dict):
        super().__init__(name, "google_sheets", raw)
        self._credentials = None
        self._sheets_client = None

    def _parse_sa_info(self):
        """Parse the service account JSON from the connection payload."""
        sa_json = self.raw.get("service_account_json", "")
        if not sa_json:
            sa_file = self.raw.get("service_account_file", "")
            if sa_file:
                return sa_file  # sentinel — handled in credentials property
            return None
        try:
            return json.loads(sa_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ConnectionParseError(
                f"Failed to parse service_account_json for '{self.name}': {exc}"
            ) from exc

    @property
    def credentials(self):
        """Return scoped google credentials for Sheets + Drive."""
        if self._credentials is not None:
            return self._credentials

        _SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        sa_info = self._parse_sa_info()

        if sa_info is None:
            raise ConnectionParseError(
                f"Google Sheets connection '{self.name}' has no "
                f"'service_account_json' or 'service_account_file'."
            )

        try:
            from google.oauth2 import service_account
        except ImportError:
            raise ImportError(
                "Install bruin-sdk[sheets] to use Google Sheets connections: "
                "pip install 'bruin-sdk[sheets]'"
            )

        if isinstance(sa_info, str):
            # sa_info is a file path (from service_account_file)
            self._credentials = service_account.Credentials.from_service_account_file(
                sa_info, scopes=_SCOPES,
            )
        else:
            self._credentials = service_account.Credentials.from_service_account_info(
                sa_info, scopes=_SCOPES,
            )

        logger.debug("Using service account credentials for '%s'", self.name)
        return self._credentials

    def sheets(self):
        """Return a cached, authorized pygsheets client."""
        if self._sheets_client is None:
            try:
                import pygsheets
            except ImportError:
                raise ImportError(
                    "Install bruin-sdk[sheets] to use Google Sheets connections: "
                    "pip install 'bruin-sdk[sheets]'"
                )
            self._sheets_client = pygsheets.authorize(custom_credentials=self.credentials)
        return self._sheets_client

    def read_sheet(self, spreadsheet, worksheet="Sheet1"):
        """Read a Google Sheets worksheet into a pandas DataFrame."""
        from bruin._sheets import _read_sheet_impl
        return _read_sheet_impl(self, spreadsheet, worksheet)

    def write_sheet(self, df, spreadsheet, worksheet="Sheet1", fit=True):
        """Write a pandas DataFrame to a Google Sheets worksheet."""
        from bruin._sheets import _write_sheet_impl
        _write_sheet_impl(self, df, spreadsheet, worksheet, fit)

    @property
    def client(self):
        """Alias for sheets() — the primary use case for this connection type."""
        return self.sheets()

    def close(self):
        """Clear cached client and credentials."""
        self._sheets_client = None
        self._credentials = None

    def __repr__(self):
        return f"GoogleSheetsConnection(name={self.name!r})"


def _create_client(conn_type: str, raw):
    """Create a database client based on connection type."""
    factories = {
        "snowflake": _create_snowflake,
        "postgres": _create_postgres,
        "redshift": _create_redshift,
        "mssql": _create_mssql,
        "synapse": _create_mssql,
        "fabric": _create_mssql,
        "mysql": _create_mysql,
        "duckdb": _create_duckdb,
        "databricks": _create_databricks,
        "clickhouse": _create_clickhouse,
        "athena": _create_athena,
        "trino": _create_trino,
        "sqlite": _create_sqlite,
        "motherduck": _create_motherduck,
        "oracle": _create_oracle,
        "db2": _create_db2,
        "hana": _create_hana,
        "spanner": _create_spanner,
        "vertica": _create_vertica,
    }
    factory = factories.get(conn_type)
    if factory is None:
        raise ConnectionTypeError(
            f"Unsupported connection type '{conn_type}'. "
            f"Supported types: google_cloud_platform, google_sheets, {', '.join(sorted(factories))}."
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
    kwargs = {
        "account": raw["account"],
        "user": raw["username"],
        "database": raw.get("database", ""),
        "warehouse": raw.get("warehouse", ""),
        "schema": raw.get("schema", ""),
        "role": raw.get("role", ""),
    }
    if raw.get("region"):
        kwargs["region"] = raw["region"]

    private_key_pem = raw.get("private_key", "")
    if private_key_pem:
        from cryptography.hazmat.primitives import serialization
        p_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None,
        )
        kwargs["private_key"] = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    else:
        kwargs["password"] = raw.get("password", "")

    return snowflake.connector.connect(**kwargs)


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
        sslmode=raw.get("ssl_mode", "allow"),
    )


def _create_redshift(raw: dict):
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[redshift] to use Redshift connections: "
            "pip install 'bruin-sdk[redshift]'"
        )
    return psycopg2.connect(
        host=raw["host"],
        port=raw.get("port", 5439),
        dbname=raw.get("database", ""),
        user=raw["username"],
        password=raw["password"],
        sslmode=raw.get("ssl_mode", "allow"),
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


def _create_databricks(raw: dict):
    try:
        from databricks import sql as databricks_sql
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[databricks] to use Databricks connections: "
            "pip install 'bruin-sdk[databricks]'"
        )
    return databricks_sql.connect(
        server_hostname=raw["host"],
        http_path=raw["path"],
        access_token=raw.get("token", ""),
        catalog=raw.get("catalog", ""),
        schema=raw.get("schema", ""),
    )


def _create_clickhouse(raw: dict):
    try:
        import clickhouse_connect
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[clickhouse] to use ClickHouse connections: "
            "pip install 'bruin-sdk[clickhouse]'"
        )
    return clickhouse_connect.get_client(
        host=raw["host"],
        port=raw.get("port", 8123),
        username=raw.get("username", "default"),
        password=raw.get("password", ""),
        database=raw.get("database", "default"),
        secure=bool(raw.get("secure", False)),
    )


def _create_athena(raw: dict):
    try:
        from pyathena import connect as athena_connect
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[athena] to use Athena connections: "
            "pip install 'bruin-sdk[athena]'"
        )
    kwargs = {
        "s3_staging_dir": raw.get("query_results_path", ""),
        "region_name": raw.get("region", ""),
    }
    if raw.get("access_key_id"):
        kwargs["aws_access_key_id"] = raw["access_key_id"]
    if raw.get("secret_access_key"):
        kwargs["aws_secret_access_key"] = raw["secret_access_key"]
    if raw.get("database"):
        kwargs["schema_name"] = raw["database"]
    if raw.get("profile"):
        kwargs["profile_name"] = raw["profile"]
    return athena_connect(**kwargs)


def _create_trino(raw: dict):
    try:
        from trino.dbapi import connect as trino_connect
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[trino] to use Trino connections: "
            "pip install 'bruin-sdk[trino]'"
        )
    kwargs = {
        "host": raw["host"],
        "port": raw.get("port", 8080),
        "user": raw.get("username", ""),
        "catalog": raw.get("catalog", ""),
        "schema": raw.get("schema", ""),
    }
    if raw.get("password"):
        from trino.auth import BasicAuthentication
        kwargs["auth"] = BasicAuthentication(raw.get("username", ""), raw["password"])
        kwargs["http_scheme"] = "https"
    return trino_connect(**kwargs)


def _create_sqlite(raw: dict):
    import sqlite3
    return sqlite3.connect(raw.get("path", ":memory:"))


def _create_motherduck(raw: dict):
    try:
        import duckdb
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[duckdb] to use MotherDuck connections: "
            "pip install 'bruin-sdk[duckdb]'"
        )
    token = raw.get("token", "")
    database = raw.get("database", "")
    conn_str = f"md:{database}" if database else "md:"
    conn = duckdb.connect(conn_str, config={"motherduck_token": token})
    return conn


def _create_oracle(raw: dict):
    try:
        import oracledb
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[oracle] to use Oracle connections: "
            "pip install 'bruin-sdk[oracle]'"
        )
    kwargs = {
        "user": raw["username"],
        "password": raw["password"],
        "host": raw["host"],
        "port": int(raw.get("port", 1521)),
    }
    if raw.get("service_name"):
        kwargs["service_name"] = raw["service_name"]
    elif raw.get("sid"):
        kwargs["sid"] = raw["sid"]
    return oracledb.connect(**kwargs)


def _create_db2(raw: dict):
    try:
        import ibm_db_dbi
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[db2] to use DB2 connections: "
            "pip install 'bruin-sdk[db2]'"
        )
    conn_str = (
        f"DATABASE={raw.get('database', '')};"
        f"HOSTNAME={raw['host']};"
        f"PORT={raw.get('port', 50000)};"
        f"PROTOCOL=TCPIP;"
        f"UID={raw['username']};"
        f"PWD={raw['password']};"
    )
    return ibm_db_dbi.connect(conn_str, "", "")


def _create_hana(raw: dict):
    try:
        from hdbcli import dbapi as hana_dbapi
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[hana] to use SAP HANA connections: "
            "pip install 'bruin-sdk[hana]'"
        )
    return hana_dbapi.connect(
        address=raw["host"],
        port=int(raw.get("port", 30015)),
        user=raw["username"],
        password=raw["password"],
        databaseName=raw.get("database", ""),
    )


def _create_spanner(raw: dict):
    try:
        from google.cloud.spanner_dbapi import connect as spanner_connect
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[spanner] to use Cloud Spanner connections: "
            "pip install 'bruin-sdk[spanner]'"
        )
    kwargs = {
        "instance_id": raw.get("instance_id", ""),
        "database_id": raw.get("database", ""),
        "project": raw.get("project_id", ""),
    }
    sa_json = raw.get("service_account_json", "")
    if sa_json:
        try:
            from google.oauth2 import service_account
        except ImportError:
            raise ImportError(
                "Install bruin-sdk[spanner] to use Spanner credentials: "
                "pip install 'bruin-sdk[spanner]'"
            )
        sa_info = json.loads(sa_json)
        kwargs["credentials"] = service_account.Credentials.from_service_account_info(sa_info)
    return spanner_connect(**kwargs)


def _create_vertica(raw: dict):
    try:
        import vertica_python
    except ImportError:
        raise ImportError(
            "Install bruin-sdk[vertica] to use Vertica connections: "
            "pip install 'bruin-sdk[vertica]'"
        )
    return vertica_python.connect(
        host=raw["host"],
        port=int(raw.get("port", 5433)),
        user=raw["username"],
        password=raw["password"],
        database=raw.get("database", ""),
    )


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

    logger.debug("Resolved connection '%s' → type=%s", name, conn_type)

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

    if conn_type == "google_sheets":
        return GoogleSheetsConnection(name, raw)

    return Connection(name, conn_type, raw)
