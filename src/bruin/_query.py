import json
import re

import pandas as pd

from bruin._connection import GCPConnection, get_connection
from bruin.exceptions import ConnectionTypeError, QueryError

_RETURNS_DATA = re.compile(
    r"^\s*(SELECT|WITH|SHOW|DESCRIBE|DESC|EXPLAIN|TABLE|VALUES)\b",
    re.IGNORECASE,
)


def _annotate_sql(sql: str) -> str:
    """Prepend a ``@bruin.config`` comment so queries are traceable."""
    from bruin._context import context

    meta = {
        "asset": context.asset_name or "",
        "type": "python_query",
        "pipeline": context.pipeline or "",
    }
    return f"-- @bruin.config: {json.dumps(meta, separators=(',', ':'))}\n{sql}"


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
            raise ConnectionTypeError(
                "No connection specified and no default connection set "
                "(BRUIN_CONNECTION env var is missing). "
                "Pass a connection name explicitly: query(sql, 'my_connection')"
            )

    conn = get_connection(connection)

    if conn.type == "generic":
        raise ConnectionTypeError(
            f"Cannot run queries against generic connection '{connection}'."
        )

    annotated = _annotate_sql(sql)

    try:
        return _execute(conn, annotated)
    except ConnectionTypeError:
        raise
    except Exception as exc:
        raise QueryError(
            f"Query failed on connection '{connection}' ({conn.type}): {exc}"
        ) from exc


def _returns_data(sql: str) -> bool:
    """Return True if *sql* is a data-returning statement."""
    # Strip leading comments (-- ... and /* ... */) before checking
    stripped = re.sub(r"--[^\n]*\n", "", sql)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    return bool(_RETURNS_DATA.match(stripped.strip()))


def _execute(conn, sql: str) -> "pd.DataFrame | None":
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

    if conn.type in ("postgres", "redshift", "mssql", "mysql"):
        if _returns_data(sql):
            return pd.read_sql(sql, conn.client)
        # For DDL/DML, execute directly
        client = conn.client
        cur = client.cursor()
        try:
            cur.execute(sql)
            client.commit()
        finally:
            cur.close()
        return None

    if conn.type == "duckdb":
        if _returns_data(sql):
            return conn.client.execute(sql).fetchdf()
        conn.client.execute(sql)
        return None

    raise ConnectionTypeError(
        f"query() does not support connection type '{conn.type}'."
    )
