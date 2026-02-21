import datetime
import json
import logging
import os

from bruin.exceptions import BruinError

logger = logging.getLogger("bruin")


def _parse_date(env_var: str) -> "datetime.date | None":
    val = os.environ.get(env_var)
    if val is None:
        return None
    logger.debug("Parsing %s=%s", env_var, val)
    try:
        return datetime.date.fromisoformat(val)
    except ValueError:
        raise BruinError(f"Invalid {env_var} value '{val}': expected ISO-8601 date (YYYY-MM-DD).")


def _parse_datetime(env_var: str) -> "datetime.datetime | None":
    val = os.environ.get(env_var)
    if val is None:
        return None
    logger.debug("Parsing %s=%s", env_var, val)
    try:
        return datetime.datetime.fromisoformat(val)
    except ValueError:
        raise BruinError(
            f"Invalid {env_var} value '{val}': expected ISO-8601 datetime (YYYY-MM-DDThh:mm:ss)."
        )


class _BruinContext:
    """Lazy accessor for BRUIN_* environment variables injected by ``bruin run``.

    Every property reads the env var fresh (no caching) so that monkeypatching
    in tests works without any special teardown.
    """

    @property
    def start_date(self) -> "datetime.date | None":
        return _parse_date("BRUIN_START_DATE")

    @property
    def end_date(self) -> "datetime.date | None":
        return _parse_date("BRUIN_END_DATE")

    @property
    def start_datetime(self) -> "datetime.datetime | None":
        return _parse_datetime("BRUIN_START_DATETIME")

    @property
    def end_datetime(self) -> "datetime.datetime | None":
        return _parse_datetime("BRUIN_END_DATETIME")

    @property
    def execution_date(self) -> "datetime.date | None":
        return _parse_date("BRUIN_EXECUTION_DATE")

    @property
    def run_id(self) -> "str | None":
        return os.environ.get("BRUIN_RUN_ID")

    @property
    def pipeline(self) -> "str | None":
        return os.environ.get("BRUIN_PIPELINE")

    @property
    def asset_name(self) -> "str | None":
        return os.environ.get("BRUIN_ASSET")

    @property
    def connection(self) -> "str | None":
        return os.environ.get("BRUIN_CONNECTION")

    @property
    def is_full_refresh(self) -> bool:
        return os.environ.get("BRUIN_FULL_REFRESH") == "1"

    @property
    def vars(self) -> dict:
        val = os.environ.get("BRUIN_VARS")
        if val is None:
            return {}
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError as exc:
            raise BruinError(f"Invalid BRUIN_VARS value: expected valid JSON. {exc}") from exc
        if not isinstance(parsed, dict):
            raise BruinError(
                f"Invalid BRUIN_VARS value: expected a JSON object, got {type(parsed).__name__}."
            )
        return parsed


context = _BruinContext()
