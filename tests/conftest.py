import json

import pytest


@pytest.fixture
def bq_connection_json():
    """Realistic BigQuery connection payload (service_account_json is double-serialized)."""
    sa_info = {
        "type": "service_account",
        "project_id": "my-gcp-project",
        "private_key_id": "key-id-123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "sa@my-gcp-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return {
        "project_id": "my-gcp-project",
        "service_account_json": json.dumps(sa_info),
    }


@pytest.fixture
def snowflake_connection_json():
    return {
        "account": "xy12345.us-east-1",
        "username": "BRUIN_USER",
        "password": "s3cret",
        "database": "ANALYTICS",
        "warehouse": "COMPUTE_WH",
        "schema": "PUBLIC",
        "role": "ANALYST",
    }


@pytest.fixture
def snowflake_keypair_connection_json():
    """Snowflake connection using key-pair auth (no password, private_key set)."""
    return {
        "account": "xy12345.us-east-1",
        "username": "BRUIN_USER",
        "password": "",
        "database": "ANALYTICS",
        "warehouse": "COMPUTE_WH",
        "schema": "PUBLIC",
        "role": "ANALYST",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7o4qne60TB3pE\n"
            "kFSFrEJma5GHSdIjauGw3sMPOjI0Ug29+VNqDuG5MXk9IJLD6RLhuGODRvFGyS+P\n"
            "rY5LjrIBKBQhAEp/2VJFXkOGJQ3IJGVk8bqv3jnYEDwIFagqnDYBPi3F7j6gfsOI\n"
            "rQbcgz0gVLMnBRBYSVbFnuHdKOfv3M3dNFCaXBJLuEFDeUSisLfHJsBanMNLqEv3\n"
            "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7o4qne60TB3pE\n"
            "-----END PRIVATE KEY-----\n"
        ),
    }


@pytest.fixture
def postgres_connection_json():
    return {
        "host": "db.example.com",
        "port": 5432,
        "username": "admin",
        "password": "s3cret",
        "database": "app_db",
        "ssl_mode": "require",
    }


@pytest.fixture
def redshift_connection_json():
    return {
        "host": "redshift-cluster.abc123.us-east-1.redshift.amazonaws.com",
        "port": 5439,
        "username": "admin",
        "password": "s3cret",
        "database": "analytics",
        "ssl_mode": "require",
    }


@pytest.fixture
def mssql_connection_json():
    return {
        "host": "sql.example.com",
        "port": 1433,
        "username": "sa",
        "password": "s3cret",
        "database": "master",
    }


@pytest.fixture
def mysql_connection_json():
    return {
        "host": "mysql.example.com",
        "port": 3306,
        "username": "root",
        "password": "s3cret",
        "database": "app",
    }


@pytest.fixture
def databricks_connection_json():
    return {
        "host": "dbc-abc123.cloud.databricks.com",
        "path": "/sql/1.0/warehouses/xyz789",
        "token": "dapi1234567890",
        "catalog": "main",
        "schema": "default",
    }


@pytest.fixture
def clickhouse_connection_json():
    return {
        "host": "ch.example.com",
        "port": 8123,
        "username": "default",
        "password": "s3cret",
        "database": "analytics",
    }


@pytest.fixture
def athena_connection_json():
    return {
        "access_key_id": "AKIA...",
        "secret_access_key": "wJal...",
        "query_results_path": "s3://my-bucket/athena-results/",
        "region": "us-east-1",
        "database": "my_db",
    }


@pytest.fixture
def trino_connection_json():
    return {
        "host": "trino.example.com",
        "port": 8080,
        "username": "analyst",
        "catalog": "hive",
        "schema": "default",
    }


@pytest.fixture
def sqlite_connection_json():
    return {
        "path": ":memory:",
    }


@pytest.fixture
def motherduck_connection_json():
    return {
        "token": "md_abc123",
        "database": "my_db",
    }


@pytest.fixture
def fabric_connection_json():
    return {
        "host": "fabric.example.com",
        "port": 1433,
        "username": "admin",
        "password": "s3cret",
        "database": "warehouse",
    }


@pytest.fixture
def oracle_connection_json():
    return {
        "host": "oracle.example.com",
        "port": 1521,
        "username": "system",
        "password": "s3cret",
        "service_name": "ORCL",
    }


@pytest.fixture
def oracle_sid_connection_json():
    return {
        "host": "oracle.example.com",
        "port": 1521,
        "username": "system",
        "password": "s3cret",
        "sid": "XE",
    }


@pytest.fixture
def db2_connection_json():
    return {
        "host": "db2.example.com",
        "port": 50000,
        "username": "db2admin",
        "password": "s3cret",
        "database": "SAMPLE",
    }


@pytest.fixture
def hana_connection_json():
    return {
        "host": "hana.example.com",
        "port": 30015,
        "username": "SYSTEM",
        "password": "s3cret",
        "database": "HDB",
    }


@pytest.fixture
def spanner_connection_json():
    return {
        "project_id": "my-gcp-project",
        "instance_id": "my-instance",
        "database": "my-db",
    }


@pytest.fixture
def vertica_connection_json():
    return {
        "host": "vertica.example.com",
        "port": 5433,
        "username": "dbadmin",
        "password": "s3cret",
        "database": "analytics",
    }
