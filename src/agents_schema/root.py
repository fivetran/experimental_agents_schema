"""Shared AGENTS.ROOT provider registry."""
from __future__ import annotations

from .destinations import Column, Destination, TableSchema

__all__ = ["ROOT", "upsert_provider_root"]

ROOT = TableSchema(
    "agents.root",
    (
        Column("provider", "varchar", nullable=False),
        Column("key", "varchar", nullable=False),
        Column("content", "text", nullable=False),
    ),
    primary_key=("provider", "key"),
)

ROOT_ENTRIES = {
    "dbt": (
        ("overview", "# dbt\nTransformation metadata from dbt manifest.json."),
        ("model", "One row per dbt model. See agents.dbt_model."),
        ("column", "One row per documented dbt model column. See agents.dbt_column."),
        ("dependency", "Direct dbt DAG edges. See agents.dbt_dependency."),
    ),
    "lookml": (
        ("overview", "# LookML\nSemantic metadata parsed from LookML files."),
        ("view", "One row per LookML view. See agents.lookml_view."),
        ("dimension", "One row per LookML dimension or dimension group. See agents.lookml_dimension."),
        ("measure", "One row per LookML measure. See agents.lookml_measure."),
        ("explore", "One row per LookML explore. See agents.lookml_explore."),
    ),
    "omni": (
        ("overview", "# Omni\nSemantic metadata parsed from Omni YAML files."),
        ("view", "One row per Omni view. See agents.omni_view."),
        ("dimension", "One row per Omni dimension. See agents.omni_dimension."),
        ("measure", "One row per Omni measure. See agents.omni_measure."),
        ("topic", "One row per Omni topic. See agents.omni_topic."),
        ("topic_join", "One row per join edge within a topic. See agents.omni_topic_join."),
    ),
    "osi": (
        ("overview", "# OSI\nOpen Semantic Interchange metadata parsed from *.osi.yaml files. The canonical semantic-layer source; other formats (e.g. LookML) reach agents.osi_* by being converted to OSI first."),
        ("model", "One row per OSI semantic model. See agents.osi_model."),
        ("dataset", "One row per OSI dataset. See agents.osi_dataset."),
        ("field", "One row per OSI dataset field. See agents.osi_field."),
        ("metric", "One row per OSI metric. See agents.osi_metric."),
        ("relationship", "One row per OSI relationship. See agents.osi_relationship."),
    ),
    "skills": (
        ("overview", "# Skills\nWarehouse-delivered agent skills published as agents.root rows."),
        ("root-convention", "Skills are rows in agents.root where key starts with skill/."),
        ("skill_use", "Optional parsed skill data-use declarations. See agents.skill_use."),
    ),
    "snowflake_semantic": (
        ("overview", "# Snowflake Semantic\nPointer rows for native Snowflake semantic views. Each key semantic_view/<name> in agents.root points to one Snowflake semantic view object. Inspect the Snowflake object for current dimensions, metrics, relationships, and query behavior."),
    ),
    "sigma": (
        ("overview", "# Sigma\nSemantic metadata parsed from Sigma data model YAML files."),
        ("data_model", "One row per Sigma data model YAML file. See agents.sigma_data_model."),
        ("element", "One row per table element in a Sigma data model. See agents.sigma_element."),
        ("column", "One row per column in a Sigma table element. See agents.sigma_column."),
        ("metric", "One row per metric in a Sigma table element. See agents.sigma_metric."),
    ),
}


def upsert_provider_root(dest: Destination, provider: str) -> None:
    rows = [(provider, key, content) for key, content in ROOT_ENTRIES[provider]]
    dest.upsert_rows(ROOT, rows)
