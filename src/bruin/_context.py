import datetime
import json
import os


class _BruinContext:
    """Lazy accessor for BRUIN_* environment variables injected by ``bruin run``.

    Every property reads the env var fresh (no caching) so that monkeypatching
    in tests works without any special teardown.
    """

    @property
    def start_date(self) -> "datetime.date | None":
        val = os.environ.get("BRUIN_START_DATE")
        if val is None:
            return None
        return datetime.date.fromisoformat(val)

    @property
    def end_date(self) -> "datetime.date | None":
        val = os.environ.get("BRUIN_END_DATE")
        if val is None:
            return None
        return datetime.date.fromisoformat(val)

    @property
    def start_datetime(self) -> "datetime.datetime | None":
        val = os.environ.get("BRUIN_START_DATETIME")
        if val is None:
            return None
        return datetime.datetime.fromisoformat(val)

    @property
    def end_datetime(self) -> "datetime.datetime | None":
        val = os.environ.get("BRUIN_END_DATETIME")
        if val is None:
            return None
        return datetime.datetime.fromisoformat(val)

    @property
    def execution_date(self) -> "datetime.date | None":
        val = os.environ.get("BRUIN_EXECUTION_DATE")
        if val is None:
            return None
        return datetime.date.fromisoformat(val)

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
        return json.loads(val)


context = _BruinContext()
