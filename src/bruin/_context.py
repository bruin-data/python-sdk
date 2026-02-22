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


def _coerce_value(value, type_def: dict):
    """Coerce a single value to match a JSON Schema type definition."""
    if value is None:
        return None
    schema_type = type_def.get("type")
    if schema_type == "string":
        return str(value)
    if schema_type == "integer":
        return int(value)
    if schema_type == "number":
        return float(value)
    if schema_type == "boolean":
        if isinstance(value, str):
            if value.lower() in ("true", "1"):
                return True
            if value.lower() in ("false", "0"):
                return False
            raise ValueError(f"Cannot convert '{value}' to boolean")
        return bool(value)
    if schema_type == "array":
        if not isinstance(value, list):
            return value
        items_def = type_def.get("items")
        if items_def:
            return [_coerce_value(item, items_def) for item in value]
        return value
    if schema_type == "object":
        if not isinstance(value, dict):
            return value
        props = type_def.get("properties", {})
        return {k: _coerce_value(v, props[k]) if k in props else v for k, v in value.items()}
    return value  # unknown type → passthrough


def _coerce_vars(values: dict, schema: dict) -> dict:
    """Apply schema-based type coercion to all variables."""
    result = {}
    for key, val in values.items():
        type_def = schema.get(key)
        if type_def:
            try:
                result[key] = _coerce_value(val, type_def)
            except (ValueError, TypeError) as exc:
                target = type_def.get("type")
                raise ValueError(
                    f"Cannot coerce variable '{key}' (value={val!r}) to {target}: {exc}"
                ) from exc
        else:
            result[key] = val
    return result


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
        schema_raw = os.environ.get("BRUIN_VARS_SCHEMA")
        if schema_raw:
            try:
                schema = json.loads(schema_raw)
            except (json.JSONDecodeError, TypeError):
                return parsed  # bad schema → return raw values
            try:
                return _coerce_vars(parsed, schema)
            except (ValueError, TypeError) as exc:
                raise BruinError(f"Cannot coerce BRUIN_VARS: {exc}") from exc
        return parsed


context = _BruinContext()
