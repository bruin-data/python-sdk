import json
import re

from bruin._connection import GCPConnection, get_connection
from bruin.exceptions import ConnectionNotFoundError, ConnectionTypeError, QueryError

_RETURNS_DATA = re.compile(
    r"^\s*(SELECT|WITH|SHOW|DESCRIBE|DESC|EXPLAIN|TABLE|VALUES)\b",
    re.IGNORECASE,
)

_CTE_DML = re.compile(
    r"\)\s*(INSERT|UPDATE|DELETE|MERGE)\b",
    re.IGNORECASE,
)

# Connection types that use the generic PEP 249 (DBAPI) cursor/read_sql path.
_DBAPI_TYPES = frozenset((
    "postgres", "redshift", "mssql", "synapse", "mysql", "athena", "trino", "sqlite",
))

# Subset of _DBAPI_TYPES that require an explicit commit() for DDL/DML.
_TRANSACTIONAL = frozenset((
    "postgres", "redshift", "mssql", "synapse", "mysql", "sqlite",
))


def _annotate_sql(sql: str) -> str:
    """Prepend a ``@bruin.config`` comment so queries are traceable."""
    from bruin._context import context

    meta = {
        "asset": context.asset_name or "",
        "type": "python_query",
        "pipeline": context.pipeline or "",
    }
    return f"-- @bruin.config: {json.dumps(meta, separators=(',', ':'))}\n{sql}"


def _run_query(conn, sql: str):
    """Core query execution shared by ``query()`` and ``Connection.query()``."""
    if conn.type == "generic":
        raise ConnectionTypeError(
            f"Cannot run queries against generic connection '{conn.name}'."
        )

    annotated = _annotate_sql(sql)

    try:
        return _execute(conn, annotated)
    except ConnectionTypeError:
        raise
    except Exception as exc:
        raise QueryError(
            f"Query failed on connection '{conn.name}' ({conn.type}): {exc}"
        ) from exc


def query(sql: str, connection: str | None = None) -> "pd.DataFrame | None":
    """Execute *sql* against a Bruin-managed connection.

    Parameters
    ----------
    sql : str
        The SQL statement to execute.
    connection : str, optional
        Connection name.  When *None*, falls back to the asset's default
        connection (``BRUIN_CONNECTION`` env var).

    Returns
    -------
    pandas.DataFrame or None
        A DataFrame for data-returning statements (SELECT, WITH, ...),
        ``None`` for DDL / DML (CREATE, INSERT, UPDATE, DELETE, ...).
    """
    if connection is None:
        from bruin._context import context
        connection = context.connection
        if connection is None:
            raise ConnectionNotFoundError(
                "No connection specified and no default connection set "
                "(BRUIN_CONNECTION env var is missing). "
                "Pass a connection name explicitly: query(sql, 'my_connection')"
            )

    conn = get_connection(connection)
    return _run_query(conn, sql)


def _returns_data(sql: str) -> bool:
    """Return True if *sql* is a data-returning statement."""
    # Strip leading comments (-- ... and /* ... */) before checking
    stripped = re.sub(r"--[^\n]*(\n|$)", "", sql)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    stripped = stripped.strip()
    if not _RETURNS_DATA.match(stripped):
        return False
    # WITH ... INSERT/UPDATE/DELETE/MERGE is DML, not data-returning
    if stripped.upper().startswith("WITH") and _CTE_DML.search(stripped):
        return False
    return True


def _execute(conn, sql: str):
    if isinstance(conn, GCPConnection):
        client = conn.bigquery()
        job = client.query(sql)
        if _returns_data(sql):
            return job.to_dataframe()
        job.result()  # wait for DDL/DML to complete
        return None

    if conn.type == "snowflake":
        cur = conn.client.cursor()
        try:
            cur.execute(sql)
            if _returns_data(sql):
                return cur.fetch_pandas_all()
            return None
        finally:
            cur.close()

    if conn.type in _DBAPI_TYPES:
        if _returns_data(sql):
            import pandas as pd
            return pd.read_sql(sql, conn.client)
        client = conn.client
        cur = client.cursor()
        try:
            cur.execute(sql)
            if conn.type in _TRANSACTIONAL:
                client.commit()
        finally:
            cur.close()
        return None

    if conn.type in ("duckdb", "motherduck"):
        if _returns_data(sql):
            return conn.client.execute(sql).fetchdf()
        conn.client.execute(sql)
        return None

    if conn.type == "databricks":
        cur = conn.client.cursor()
        try:
            cur.execute(sql)
            if _returns_data(sql):
                import pandas as pd
                cols = [desc[0] for desc in cur.description]
                return pd.DataFrame(cur.fetchall(), columns=cols)
            return None
        finally:
            cur.close()

    if conn.type == "clickhouse":
        if _returns_data(sql):
            result = conn.client.query(sql)
            import pandas as pd
            return pd.DataFrame(
                result.result_rows,
                columns=result.column_names,
            )
        conn.client.command(sql)
        return None

    raise ConnectionTypeError(
        f"query() does not support connection type '{conn.type}'."
    )
