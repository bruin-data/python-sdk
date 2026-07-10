"""Bruin SDK — zero-boilerplate access to Bruin-managed connections and context."""

from importlib.metadata import PackageNotFoundError, version

from bruin._connection import get_connection
from bruin._context import context
from bruin._query import query

try:
    __version__ = version("bruin-sdk")
except PackageNotFoundError:  # source tree without an installed distribution
    __version__ = "0.0.0.dev0"

__all__ = ["__version__", "context", "get_connection", "query"]
