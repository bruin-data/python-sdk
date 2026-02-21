class BruinError(Exception):
    """Base exception for all Bruin SDK errors."""


class ConnectionNotFoundError(BruinError):
    """Raised when a requested connection name is not found in the environment."""


class ConnectionParseError(BruinError):
    """Raised when connection JSON cannot be parsed."""


class ConnectionTypeError(BruinError):
    """Raised when a connection type is unknown or unsupported."""


class QueryError(BruinError):
    """Raised when a SQL query fails to execute."""
