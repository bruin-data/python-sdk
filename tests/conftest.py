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
