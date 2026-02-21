import logging

from bruin._connection import get_connection
from bruin.exceptions import ConnectionNotFoundError, ConnectionTypeError

logger = logging.getLogger("bruin")


def _get_sheets_client(connection):
    """Resolve *connection* to a ``(Connection, pygsheets.Client)`` pair.

    Works with both ``google_cloud_platform`` and ``google_sheets`` connection types.
    """
    if connection is None:
        from bruin._context import context

        connection = context.connection
        if connection is None:
            raise ConnectionNotFoundError(
                "No connection specified and no default connection set "
                "(BRUIN_CONNECTION env var is missing). "
                "Pass a connection name explicitly: read_sheet(spreadsheet, connection='my_gcp')"
            )

    conn = get_connection(connection)

    if not hasattr(conn, "sheets"):
        raise ConnectionTypeError(
            f"Connection '{conn.name}' ({conn.type}) does not support Google Sheets."
        )
    return conn, conn.sheets()


def _read_sheet_impl(conn, spreadsheet, worksheet="Sheet1"):
    """Core read logic that operates on an already-resolved connection object."""
    gc = conn.sheets()
    logger.debug("Reading '%s'.'%s' via '%s'", spreadsheet, worksheet, conn.name)

    sh = gc.open_by_key(spreadsheet)
    wks = sh.worksheet_by_title(worksheet)
    df = wks.get_as_df(
        numerize=True,
        empty_value="",
        include_tailing_empty=True,
        include_tailing_empty_rows=False,
    )

    logger.debug("Read %d rows x %d cols", len(df), len(df.columns))
    return df


def _write_sheet_impl(conn, df, spreadsheet, worksheet="Sheet1", fit=True):
    """Core write logic that operates on an already-resolved connection object."""
    gc = conn.sheets()
    logger.debug(
        "Writing %d rows to '%s'.'%s' via '%s'",
        len(df), spreadsheet, worksheet, conn.name,
    )

    sh = gc.open_by_key(spreadsheet)
    wks = sh.worksheet_by_title(worksheet)
    wks.clear()
    wks.set_dataframe(df, start="A1", fit=fit, nan="", escape_formulae=True)

    logger.debug("Write complete")


def read_sheet(spreadsheet, worksheet="Sheet1", connection=None):
    """Read a Google Sheets worksheet into a pandas DataFrame.

    Parameters
    ----------
    spreadsheet : str
        The spreadsheet ID (the long string in the Google Sheets URL).
    worksheet : str
        The worksheet tab title.  Defaults to ``"Sheet1"``.
    connection : str, optional
        Connection name.  When *None*, falls back to the asset's default
        connection (``BRUIN_CONNECTION`` env var).

    Returns
    -------
    pandas.DataFrame
    """
    conn, gc = _get_sheets_client(connection)
    logger.debug("Reading '%s'.'%s' via '%s'", spreadsheet, worksheet, conn.name)

    sh = gc.open_by_key(spreadsheet)
    wks = sh.worksheet_by_title(worksheet)
    df = wks.get_as_df(
        numerize=True,
        empty_value="",
        include_tailing_empty=True,
        include_tailing_empty_rows=False,
    )

    logger.debug("Read %d rows x %d cols", len(df), len(df.columns))
    return df


def write_sheet(df, spreadsheet, worksheet="Sheet1", connection=None, fit=True):
    """Write a pandas DataFrame to a Google Sheets worksheet.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to write.
    spreadsheet : str
        The spreadsheet ID (the long string in the Google Sheets URL).
    worksheet : str
        The worksheet tab title.  Defaults to ``"Sheet1"``.
    connection : str, optional
        Connection name.  When *None*, falls back to the asset's default
        connection (``BRUIN_CONNECTION`` env var).
    fit : bool
        If *True* (default), resize the sheet to match the DataFrame dimensions.
    """
    conn, gc = _get_sheets_client(connection)
    logger.debug(
        "Writing %d rows to '%s'.'%s' via '%s'",
        len(df), spreadsheet, worksheet, conn.name,
    )

    sh = gc.open_by_key(spreadsheet)
    wks = sh.worksheet_by_title(worksheet)
    wks.clear()
    wks.set_dataframe(df, start="A1", fit=fit, nan="", escape_formulae=True)

    logger.debug("Write complete")
