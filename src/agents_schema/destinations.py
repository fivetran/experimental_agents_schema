"""Warehouse destinations for agents-schema writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .agents_schema_writer import (
    AgentsSchemaWriter,
    BigQueryAgentsSchemaWriter,
    ClickHouseAgentsSchemaWriter,
    Column,
    DatabricksAgentsSchemaWriter,
    SnowflakeAgentsSchemaWriter,
    TableSchema,
)
from .agents_schema_writer.snowflake import (
    _create_table_if_not_exists_sql,
    _create_table_sql,
    _delete_sql,
    _insert_sql,
    _merge_sql,
    load_private_key,
)
from .config import SUPPORTED_WAREHOUSE_TYPES, ConfigError, warehouse_type

Destination = AgentsSchemaWriter


class SnowflakeDestination(SnowflakeAgentsSchemaWriter):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        import snowflake.connector

        if connect_kwargs is None:
            if config is None:
                raise ConfigError("SnowflakeDestination requires config or connect_kwargs")
            connect_kwargs = _snowflake_connect_kwargs(config)
        super().__init__(snowflake.connector.connect(**connect_kwargs))


class DatabricksDestination(DatabricksAgentsSchemaWriter):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connect_kwargs: dict[str, Any] | None = None,
    ) -> None:
        import databricks.sql

        if connect_kwargs is None:
            if config is None:
                raise ConfigError("DatabricksDestination requires config or connect_kwargs")
            connect_kwargs = _databricks_connect_kwargs(config)
        super().__init__(databricks.sql.connect(**connect_kwargs))


class ClickHouseDestination(ClickHouseAgentsSchemaWriter):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        if client is None:
            import clickhouse_connect

            if config is None:
                raise ConfigError("ClickHouseDestination requires config or client")
            client = clickhouse_connect.get_client(**_clickhouse_connect_kwargs(config))
        super().__init__(client)


class BigQueryDestination(BigQueryAgentsSchemaWriter):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        client: Any | None = None,
        credentials_info: dict[str, Any] | None = None,
        project_id: str | None = None,
        location: str | None = None,
    ) -> None:
        if client is None:
            from google.cloud import bigquery
            from google.oauth2.service_account import Credentials

            if credentials_info is None or project_id is None:
                if config is None:
                    raise ConfigError("BigQueryDestination requires config or client")
                credentials_info, project_id, location = _bigquery_credentials(config)
            credentials = Credentials.from_service_account_info(credentials_info)
            client = bigquery.Client(credentials=credentials, project=project_id)
        if project_id is None:
            raise ConfigError("BigQueryDestination requires project_id")
        super().__init__(client, project_id, location)


def open_destination(cfg: dict[str, Any]) -> Destination:
    dest_type = warehouse_type(cfg)
    if dest_type == "snowflake":
        return SnowflakeDestination(cfg)
    if dest_type == "databricks":
        return DatabricksDestination(cfg)
    if dest_type in {"bigquery", "big_query"}:
        return BigQueryDestination(cfg)
    if dest_type == "clickhouse":
        return ClickHouseDestination(cfg)
    raise ConfigError(f"unsupported destination type: {dest_type}")


def warehouse_credentials_from_env() -> dict[str, Any]:
    raw = os.environ.get("WAREHOUSE_CREDENTIALS")
    if not raw:
        raise ConfigError("missing required WAREHOUSE_CREDENTIALS secret")
    destination = _parse_warehouse_credentials(raw)
    destination_type = destination.get("type")
    if not isinstance(destination_type, str) or not destination_type:
        raise ConfigError("WAREHOUSE_CREDENTIALS.type is required")
    if destination_type not in SUPPORTED_WAREHOUSE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_WAREHOUSE_TYPES))
        raise ConfigError(
            f"unsupported WAREHOUSE_CREDENTIALS.type {destination_type!r}; supported types: {supported}"
        )
    return destination


def warehouse_type_from_env() -> str:
    return str(warehouse_credentials_from_env()["type"])


def _parse_warehouse_credentials(raw: str) -> dict[str, Any]:
    try:
        destination = json.loads(raw)
    except json.JSONDecodeError:
        try:
            destination = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ConfigError(f"WAREHOUSE_CREDENTIALS is not valid JSON or YAML: {e}") from e
    if not isinstance(destination, dict):
        raise ConfigError("WAREHOUSE_CREDENTIALS must be a JSON or YAML object")
    return destination


def _snowflake_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "snowflake":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be snowflake")
    return _snowflake_connect_kwargs_from_secret(destination)


def _snowflake_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    required = ["account", "user", "warehouse", "database"]
    missing = [name for name in required if not destination.get(name)]
    has_password = bool(destination.get("password"))
    has_private_key_pem = bool(destination.get("private_key_pem"))
    has_private_key_path = bool(destination.get("private_key_path"))
    if not has_password and not has_private_key_pem and not has_private_key_path:
        missing.append("password, private_key_pem, or private_key_path")
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

    kwargs: dict[str, Any] = {
        "account": destination["account"],
        "user": destination["user"],
        "warehouse": destination["warehouse"],
        "database": destination["database"],
    }
    if role := destination.get("role"):
        kwargs["role"] = role
    passphrase = destination.get("private_key_passphrase")
    if has_private_key_pem:
        kwargs["private_key"] = load_private_key(
            destination["private_key_pem"].encode(),
            passphrase,
        )
    elif has_private_key_path:
        kwargs["private_key"] = load_private_key(
            Path(destination["private_key_path"]).read_bytes(),
            passphrase,
        )
    else:
        kwargs["password"] = destination["password"]
    return kwargs


def _databricks_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "databricks":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be databricks")
    return _databricks_connect_kwargs_from_secret(destination)


def _databricks_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    host = (
        destination.get("host")
        or destination.get("server_host_name")
        or destination.get("serverHostName")
    )
    token = (
        destination.get("token")
        or destination.get("access_token")
        or destination.get("personal_access_token")
        or destination.get("personalAccessToken")
    )
    required = {
        "host": host,
        "http_path": destination.get("http_path") or destination.get("httpPath"),
        "catalog": destination.get("catalog"),
        "token": token,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: " + ", ".join(missing))

    return {
        "server_hostname": required["host"],
        "http_path": required["http_path"],
        "catalog": required["catalog"],
        "access_token": required["token"],
    }


def _clickhouse_connect_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") != "clickhouse":
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be clickhouse")
    return _clickhouse_connect_kwargs_from_secret(destination)


def _clickhouse_connect_kwargs_from_secret(destination: dict[str, Any]) -> dict[str, Any]:
    host = destination.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: host")

    secure = destination.get("secure")
    if secure is None:
        secure = True
    elif isinstance(secure, str):
        lowered = secure.strip().lower()
        if lowered in {"true", "1", "yes"}:
            secure = True
        elif lowered in {"false", "0", "no"}:
            secure = False
        else:
            raise ConfigError(f"WAREHOUSE_CREDENTIALS.secure must be a boolean, got {secure!r}")
    elif not isinstance(secure, bool):
        raise ConfigError(f"WAREHOUSE_CREDENTIALS.secure must be a boolean, got {secure!r}")
    kwargs: dict[str, Any] = {
        "host": host.strip(),
        "username": destination.get("user") or destination.get("username") or "default",
        "password": destination.get("password") or "",
        "secure": secure,
    }
    port = destination.get("port")
    if port is not None:
        if isinstance(port, bool) or not isinstance(port, (int, str)):
            raise ConfigError(
                f"WAREHOUSE_CREDENTIALS.port must be an integer from 1 to 65535, got {port!r}"
            )
        try:
            parsed_port = int(port)
        except ValueError as e:
            raise ConfigError(
                f"WAREHOUSE_CREDENTIALS.port must be an integer from 1 to 65535, got {port!r}"
            ) from e
        if not 1 <= parsed_port <= 65535:
            raise ConfigError(
                f"WAREHOUSE_CREDENTIALS.port must be an integer from 1 to 65535, got {port!r}"
            )
        kwargs["port"] = parsed_port
    return kwargs


def _bigquery_credentials(cfg: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
    destination = warehouse_credentials_from_env()
    if destination.get("type") not in {"bigquery", "big_query"}:
        raise ConfigError("WAREHOUSE_CREDENTIALS.type must be bigquery")
    return _bigquery_credentials_from_secret(destination)


def _bigquery_credentials_from_secret(destination: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
    project_id = destination.get("project_id") or destination.get("projectId") or destination.get("project")
    if not project_id:
        raise ConfigError("WAREHOUSE_CREDENTIALS missing keys: project_id")

    credentials_info = destination.get("credentials_json") or destination.get("credentialsJson")
    if isinstance(credentials_info, str):
        try:
            credentials_info = json.loads(credentials_info)
        except json.JSONDecodeError as e:
            raise ConfigError(f"WAREHOUSE_CREDENTIALS.credentials_json is not valid JSON: {e}") from e
    if credentials_info is None:
        credentials_info = _bigquery_service_account_from_flat_secret(destination)
    if not isinstance(credentials_info, dict):
        raise ConfigError("WAREHOUSE_CREDENTIALS.credentials_json must be a JSON object")

    required = ["private_key", "client_email"]
    missing = [name for name in required if not credentials_info.get(name)]
    if missing:
        raise ConfigError("WAREHOUSE_CREDENTIALS.credentials_json missing keys: " + ", ".join(missing))
    credentials_info = {"type": "service_account", **credentials_info}
    return credentials_info, str(project_id), _optional_string(destination.get("location"))


def _bigquery_service_account_from_flat_secret(destination: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": destination.get("service_account_type") or "service_account",
        "project_id": destination.get("service_account_project_id") or destination.get("project_id"),
        "private_key_id": destination.get("private_key_id", ""),
        "private_key": destination.get("private_key", ""),
        "client_email": destination.get("client_email", ""),
        "client_id": destination.get("client_id", ""),
        "auth_uri": destination.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
        "token_uri": destination.get("token_uri", "https://oauth2.googleapis.com/token"),
        "auth_provider_x509_cert_url": destination.get(
            "auth_provider_x509_cert_url",
            "https://www.googleapis.com/oauth2/v1/certs",
        ),
        "client_x509_cert_url": destination.get("client_x509_cert_url", ""),
    }


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


__all__ = [
    "BigQueryDestination",
    "ClickHouseDestination",
    "Column",
    "DatabricksDestination",
    "Destination",
    "SnowflakeDestination",
    "TableSchema",
    "_bigquery_credentials_from_secret",
    "_clickhouse_connect_kwargs_from_secret",
    "_create_table_if_not_exists_sql",
    "_create_table_sql",
    "_databricks_connect_kwargs_from_secret",
    "_delete_sql",
    "_insert_sql",
    "_merge_sql",
    "_snowflake_connect_kwargs_from_secret",
    "open_destination",
    "warehouse_credentials_from_env",
    "warehouse_type_from_env",
]
