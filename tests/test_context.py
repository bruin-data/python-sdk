import datetime
import json

import pytest

from bruin import context
from bruin.exceptions import BruinError


class TestStartDate:
    def test_returns_date(self, monkeypatch):
        monkeypatch.setenv("BRUIN_START_DATE", "2024-01-15")
        assert context.start_date == datetime.date(2024, 1, 15)

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_START_DATE", raising=False)
        assert context.start_date is None


class TestEndDate:
    def test_returns_date(self, monkeypatch):
        monkeypatch.setenv("BRUIN_END_DATE", "2024-06-30")
        assert context.end_date == datetime.date(2024, 6, 30)

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_END_DATE", raising=False)
        assert context.end_date is None


class TestStartDatetime:
    def test_returns_datetime(self, monkeypatch):
        monkeypatch.setenv("BRUIN_START_DATETIME", "2024-01-15T10:30:00")
        assert context.start_datetime == datetime.datetime(2024, 1, 15, 10, 30, 0)

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_START_DATETIME", raising=False)
        assert context.start_datetime is None


class TestEndDatetime:
    def test_returns_datetime(self, monkeypatch):
        monkeypatch.setenv("BRUIN_END_DATETIME", "2024-06-30T23:59:59")
        assert context.end_datetime == datetime.datetime(2024, 6, 30, 23, 59, 59)

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_END_DATETIME", raising=False)
        assert context.end_datetime is None


class TestExecutionDate:
    def test_returns_date(self, monkeypatch):
        monkeypatch.setenv("BRUIN_EXECUTION_DATE", "2024-03-01")
        assert context.execution_date == datetime.date(2024, 3, 1)

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_EXECUTION_DATE", raising=False)
        assert context.execution_date is None


class TestRunId:
    def test_returns_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_RUN_ID", "abc-123")
        assert context.run_id == "abc-123"

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_RUN_ID", raising=False)
        assert context.run_id is None


class TestPipeline:
    def test_returns_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_PIPELINE", "my_pipeline")
        assert context.pipeline == "my_pipeline"

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_PIPELINE", raising=False)
        assert context.pipeline is None


class TestAssetName:
    def test_returns_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_ASSET", "my_asset")
        assert context.asset_name == "my_asset"

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_ASSET", raising=False)
        assert context.asset_name is None


class TestConnection:
    def test_returns_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_CONNECTION", "my_bigquery")
        assert context.connection == "my_bigquery"

    def test_returns_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_CONNECTION", raising=False)
        assert context.connection is None


class TestIsFullRefresh:
    def test_true_when_set_to_1(self, monkeypatch):
        monkeypatch.setenv("BRUIN_FULL_REFRESH", "1")
        assert context.is_full_refresh is True

    def test_false_when_set_to_0(self, monkeypatch):
        monkeypatch.setenv("BRUIN_FULL_REFRESH", "0")
        assert context.is_full_refresh is False

    def test_false_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_FULL_REFRESH", raising=False)
        assert context.is_full_refresh is False

    def test_false_when_other_value(self, monkeypatch):
        monkeypatch.setenv("BRUIN_FULL_REFRESH", "true")
        assert context.is_full_refresh is False


class TestVars:
    def test_returns_parsed_dict(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"key": "value", "count": 42, "flag": True}),
        )
        result = context.vars
        assert result == {"key": "value", "count": 42, "flag": True}

    def test_preserves_types(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"s": "hello", "i": 7, "f": 3.14, "b": False, "a": [1, 2]}),
        )
        v = context.vars
        assert isinstance(v["s"], str)
        assert isinstance(v["i"], int)
        assert isinstance(v["f"], float)
        assert isinstance(v["b"], bool)
        assert isinstance(v["a"], list)

    def test_returns_empty_dict_when_missing(self, monkeypatch):
        monkeypatch.delenv("BRUIN_VARS", raising=False)
        assert context.vars == {}


class TestMalformedValues:
    def test_invalid_date_raises_bruin_error(self, monkeypatch):
        monkeypatch.setenv("BRUIN_START_DATE", "not-a-date")
        with pytest.raises(BruinError, match="Invalid BRUIN_START_DATE"):
            _ = context.start_date

    def test_invalid_datetime_raises_bruin_error(self, monkeypatch):
        monkeypatch.setenv("BRUIN_START_DATETIME", "garbage")
        with pytest.raises(BruinError, match="Invalid BRUIN_START_DATETIME"):
            _ = context.start_datetime

    def test_invalid_vars_json_raises_bruin_error(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", "{bad json")
        with pytest.raises(BruinError, match="Invalid BRUIN_VARS"):
            _ = context.vars

    def test_non_dict_vars_raises_bruin_error(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", "[1, 2, 3]")
        with pytest.raises(BruinError, match="expected a JSON object"):
            _ = context.vars


class TestFreshReads:
    def test_changing_env_var_reflects_immediately(self, monkeypatch):
        monkeypatch.setenv("BRUIN_RUN_ID", "first")
        assert context.run_id == "first"
        monkeypatch.setenv("BRUIN_RUN_ID", "second")
        assert context.run_id == "second"
