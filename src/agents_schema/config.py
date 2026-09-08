"""Shared configuration validation for agents-schema."""
from __future__ import annotations

from typing import Any


class ConfigError(Exception):
    """Raised when CLI arguments or environment settings are invalid."""


SUPPORTED_WAREHOUSE_TYPES = {"big_query", "bigquery", "clickhouse", "databricks", "snowflake"}


def warehouse_type(cfg: dict[str, Any]) -> str:
    warehouse = cfg.get("warehouse")
    if warehouse is None:
        raise ConfigError("warehouse.type is required")
    if not isinstance(warehouse, dict):
        raise ConfigError("warehouse must be a mapping when provided")
    wh_type = warehouse.get("type")
    if not isinstance(wh_type, str) or not wh_type:
        raise ConfigError("warehouse.type is required")
    if wh_type not in SUPPORTED_WAREHOUSE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_WAREHOUSE_TYPES))
        raise ConfigError(f"unsupported warehouse.type {wh_type!r}; supported types: {supported}")
    return wh_type
