"""Helpers for reading dbt profiles.yml enough to run dbt parse."""
from __future__ import annotations

from pathlib import Path

import yaml

from .config import ConfigError

DBT_ADAPTER_PACKAGE_BY_PROFILE_TYPE = {
    "bigquery": "dbt-bigquery",
    "clickhouse": "dbt-clickhouse",
    "databricks": "dbt-databricks",
    "snowflake": "dbt-snowflake",
}


def dbt_adapter_package_from_profiles_file(
    profiles_path: Path,
    profile_name: str,
    target_name: str | None = None,
) -> str:
    profile_type = dbt_profile_type_from_profiles_file(profiles_path, profile_name, target_name)
    try:
        return DBT_ADAPTER_PACKAGE_BY_PROFILE_TYPE[profile_type]
    except KeyError as e:
        supported = ", ".join(sorted(DBT_ADAPTER_PACKAGE_BY_PROFILE_TYPE))
        raise ConfigError(
            f"dbt profile {profile_name!r} uses adapter type {profile_type!r}; supported types: {supported}"
        ) from e


def dbt_profile_type_from_profiles_file(
    profiles_path: Path,
    profile_name: str,
    target_name: str | None = None,
) -> str:
    try:
        profiles = yaml.safe_load(profiles_path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"{profiles_path} is not valid YAML: {e}") from e
    if not isinstance(profiles, dict):
        raise ConfigError(f"{profiles_path} must contain a YAML mapping")

    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        available = ", ".join(sorted(str(name) for name in profiles)) or "none"
        raise ConfigError(f"dbt profile {profile_name!r} not found in {profiles_path}; available profiles: {available}")

    outputs = profile.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ConfigError(f"dbt profile {profile_name!r} must define outputs")

    selected_target = target_name or profile.get("target")
    if not selected_target:
        if len(outputs) == 1:
            selected_target = next(iter(outputs))
        else:
            available_targets = ", ".join(sorted(str(name) for name in outputs))
            raise ConfigError(
                f"dbt profile {profile_name!r} does not define target; pass dbt-target. "
                f"Available targets: {available_targets}"
            )

    output = outputs.get(selected_target)
    if not isinstance(output, dict):
        available_targets = ", ".join(sorted(str(name) for name in outputs))
        raise ConfigError(
            f"dbt target {selected_target!r} not found in profile {profile_name!r}; "
            f"available targets: {available_targets}"
        )

    profile_type = output.get("type")
    if not isinstance(profile_type, str) or not profile_type:
        raise ConfigError(f"dbt profile {profile_name!r} target {selected_target!r} must define type")
    return profile_type.lower()
