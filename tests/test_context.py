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


class TestVarsWithSchema:
    """Tests for type-aware variable coercion using BRUIN_VARS_SCHEMA."""

    def test_integer_from_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"count": "42"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"count": {"type": "integer"}}))
        assert context.vars == {"count": 42}

    def test_number_from_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"rate": "3.14"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"rate": {"type": "number"}}))
        assert context.vars == {"rate": 3.14}

    def test_boolean_true_from_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"flag": "true"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"flag": {"type": "boolean"}}))
        assert context.vars == {"flag": True}

    def test_boolean_false_from_string(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"flag": "false"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"flag": {"type": "boolean"}}))
        assert context.vars == {"flag": False}

    def test_boolean_from_int(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"flag": 1}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"flag": {"type": "boolean"}}))
        assert context.vars == {"flag": True}

    def test_string_passthrough(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"env": "prod"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"env": {"type": "string"}}))
        assert context.vars == {"env": "prod"}

    def test_integer_already_int(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"count": 42}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"count": {"type": "integer"}}))
        assert context.vars == {"count": 42}

    def test_null_passthrough(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"x": None}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"x": {"type": "integer"}}))
        assert context.vars == {"x": None}

    def test_array_coercion(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"ids": ["1", "2"]}))
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({"ids": {"type": "array", "items": {"type": "integer"}}}),
        )
        assert context.vars == {"ids": [1, 2]}

    def test_object_coercion(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"cfg": {"port": "8080"}}))
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({"cfg": {"type": "object", "properties": {"port": {"type": "integer"}}}}),
        )
        assert context.vars == {"cfg": {"port": 8080}}

    def test_nested_object_in_object(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"db": {"host": "localhost", "opts": {"timeout": "30", "retries": "3"}}}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "db": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string"},
                        "opts": {
                            "type": "object",
                            "properties": {
                                "timeout": {"type": "integer"},
                                "retries": {"type": "integer"},
                            },
                        },
                    },
                },
            }),
        )
        assert context.vars == {"db": {"host": "localhost", "opts": {"timeout": 30, "retries": 3}}}

    def test_array_of_objects(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"users": [{"name": "alice", "age": "30"}, {"name": "bob", "age": "25"}]}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "users": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"},
                        },
                    },
                },
            }),
        )
        assert context.vars == {"users": [{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]}

    def test_object_with_array_property(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"config": {"name": "prod", "ports": ["80", "443"]}}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "config": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "ports": {"type": "array", "items": {"type": "integer"}},
                    },
                },
            }),
        )
        assert context.vars == {"config": {"name": "prod", "ports": [80, 443]}}

    def test_array_without_items_schema(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"tags": ["a", "b", "c"]}))
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({"tags": {"type": "array"}}),
        )
        assert context.vars == {"tags": ["a", "b", "c"]}

    def test_object_with_extra_keys_not_in_properties(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"cfg": {"port": "8080", "debug": "true", "label": "dev"}}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "cfg": {
                    "type": "object",
                    "properties": {"port": {"type": "integer"}},
                },
            }),
        )
        assert context.vars == {"cfg": {"port": 8080, "debug": "true", "label": "dev"}}

    def test_deeply_nested_three_levels(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({
                "infra": {
                    "cluster": {
                        "node": {"cpu": "4", "memory": "16384", "gpu": "true"},
                    },
                },
            }),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "infra": {
                    "type": "object",
                    "properties": {
                        "cluster": {
                            "type": "object",
                            "properties": {
                                "node": {
                                    "type": "object",
                                    "properties": {
                                        "cpu": {"type": "integer"},
                                        "memory": {"type": "integer"},
                                        "gpu": {"type": "boolean"},
                                    },
                                },
                            },
                        },
                    },
                },
            }),
        )
        assert context.vars == {
            "infra": {"cluster": {"node": {"cpu": 4, "memory": 16384, "gpu": True}}}
        }

    def test_multiple_vars_mixed_types(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({
                "env": "production",
                "replicas": "3",
                "rate_limit": "1.5",
                "debug": "false",
                "regions": ["us-east-1", "eu-west-1"],
                "db": {"port": "5432", "ssl": "true"},
            }),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "env": {"type": "string"},
                "replicas": {"type": "integer"},
                "rate_limit": {"type": "number"},
                "debug": {"type": "boolean"},
                "regions": {"type": "array", "items": {"type": "string"}},
                "db": {
                    "type": "object",
                    "properties": {
                        "port": {"type": "integer"},
                        "ssl": {"type": "boolean"},
                    },
                },
            }),
        )
        assert context.vars == {
            "env": "production",
            "replicas": 3,
            "rate_limit": 1.5,
            "debug": False,
            "regions": ["us-east-1", "eu-west-1"],
            "db": {"port": 5432, "ssl": True},
        }

    def test_array_of_arrays(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"matrix": [["1", "2"], ["3", "4"]]}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({
                "matrix": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
            }),
        )
        assert context.vars == {"matrix": [[1, 2], [3, 4]]}

    def test_object_without_properties_schema(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"meta": {"foo": "bar", "n": "1"}}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({"meta": {"type": "object"}}),
        )
        assert context.vars == {"meta": {"foo": "bar", "n": "1"}}

    def test_no_schema_returns_raw(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"count": "42"}))
        monkeypatch.delenv("BRUIN_VARS_SCHEMA", raising=False)
        assert context.vars == {"count": "42"}

    def test_var_not_in_schema_passthrough(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"a": "1", "b": "2"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"a": {"type": "integer"}}))
        assert context.vars == {"a": 1, "b": "2"}

    def test_coercion_failure_raises(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"count": "abc"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", json.dumps({"count": {"type": "integer"}}))
        with pytest.raises(BruinError, match="Cannot coerce variable 'count'"):
            _ = context.vars

    def test_coercion_failure_in_nested_object_includes_path(self, monkeypatch):
        monkeypatch.setenv(
            "BRUIN_VARS",
            json.dumps({"cfg": {"port": "not_a_number"}}),
        )
        monkeypatch.setenv(
            "BRUIN_VARS_SCHEMA",
            json.dumps({"cfg": {"type": "object", "properties": {"port": {"type": "integer"}}}}),
        )
        with pytest.raises(BruinError, match="Cannot coerce variable 'cfg'"):
            _ = context.vars

    def test_invalid_schema_json_ignored(self, monkeypatch):
        monkeypatch.setenv("BRUIN_VARS", json.dumps({"x": "1"}))
        monkeypatch.setenv("BRUIN_VARS_SCHEMA", "{bad json")
        assert context.vars == {"x": "1"}


class TestFreshReads:
    def test_changing_env_var_reflects_immediately(self, monkeypatch):
        monkeypatch.setenv("BRUIN_RUN_ID", "first")
        assert context.run_id == "first"
        monkeypatch.setenv("BRUIN_RUN_ID", "second")
        assert context.run_id == "second"
