"""Skills connector: writes markdown skills into AGENTS.ROOT."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

import importlib.resources

from .config import ConfigError, warehouse_type
from .destinations import Column, Destination, TableSchema, open_destination
from .root import ROOT, upsert_provider_root

__all__ = ["SKILL_USE", "publish_builtin_skill", "publish_skill", "run"]

SKILL_USE = TableSchema(
    "agents.skill_use",
    (
        Column("provider", "varchar", nullable=False),
        Column("skill_key", "varchar", nullable=False),
        Column("use_kind", "varchar", nullable=False),
        Column("object_ref", "varchar", nullable=False),
    ),
    primary_key=("provider", "skill_key", "use_kind", "object_ref"),
)


@dataclass(frozen=True)
class SkillFile:
    key: str
    content: str
    uses: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...] = ()


def run(cfg: dict) -> None:
    metadata = cfg["metadata_connection"]
    skills_dir = Path(metadata["path"])
    provider = metadata["provider"]
    skills = _load_skill_files(skills_dir)
    root_rows = [(provider, skill.key, skill.content) for skill in skills]
    use_rows = [
        (provider, skill.key, use_kind, object_ref)
        for skill in skills
        for use_kind, object_ref in skill.uses
    ]

    for skill in skills:
        for warning in skill.warnings:
            print(f"  skills: warning: {skill.key}: {warning}", file=sys.stderr)

    with open_destination(cfg) as dest:
        upsert_provider_root(dest, "skills")
        dest.upsert_rows(ROOT, root_rows)
        dest.replace_table(SKILL_USE)
        if use_rows:
            dest.insert_rows(SKILL_USE, use_rows)
        publish_builtin_skill(dest, warehouse_type(cfg))

    print(f"  skills:   {len(root_rows)} skills, {len(use_rows)} uses")


BUILTIN_ANALYST_KEY = "skill/agents-schema-analyst"
_ANALYST_SKILL_FILES = {
    "snowflake": "agents-schema-analyst-snowflake.md",
    "databricks": "agents-schema-analyst-databricks.md",
    "bigquery": "agents-schema-analyst-bigquery.md",
    "big_query": "agents-schema-analyst-bigquery.md",
    "clickhouse": "agents-schema-analyst-clickhouse.md",
}


def publish_builtin_skill(dest: Destination, warehouse_type: str) -> None:
    content = _load_builtin_analyst_skill(warehouse_type)
    publish_skill(dest, "skills", BUILTIN_ANALYST_KEY, content)


def _load_builtin_analyst_skill(warehouse_type: str) -> str:
    filename = _ANALYST_SKILL_FILES.get(warehouse_type)
    if filename is None:
        raise ConfigError(f"no built-in analyst skill for warehouse type: {warehouse_type}")
    return (
        importlib.resources.files("agents_schema.builtin_skills")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def publish_skill(dest: Destination, provider: str, skill_key: str, content: str) -> SkillFile:
    uses, warnings = _parse_uses_frontmatter(content)
    skill = SkillFile(key=skill_key, content=content, uses=uses, warnings=warnings)
    root_rows = [(provider, skill.key, skill.content)]
    use_rows = [
        (provider, skill.key, use_kind, object_ref)
        for use_kind, object_ref in skill.uses
    ]

    upsert_provider_root(dest, "skills")
    dest.upsert_rows(ROOT, root_rows)
    dest.delete_rows(SKILL_USE, ("provider", "skill_key"), [(provider, skill.key)])
    if use_rows:
        dest.upsert_rows(SKILL_USE, use_rows)
    return skill


def _load_skill_files(skills_dir: Path) -> list[SkillFile]:
    files = sorted(path for path in skills_dir.rglob("*.md") if path.is_file())
    if not files:
        raise FileNotFoundError(f"no *.md skill files found in {skills_dir}")
    return [_load_skill_file(skills_dir, path) for path in files]


def _load_skill_file(skills_dir: Path, path: Path) -> SkillFile:
    rel = path.relative_to(skills_dir)
    key = "skill/" + rel.with_suffix("").as_posix()
    content = path.read_text()
    uses, warnings = _parse_uses_frontmatter(content)
    return SkillFile(key=key, content=content, uses=uses, warnings=warnings)


def _parse_uses_frontmatter(content: str) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    frontmatter, warning = _frontmatter(content)
    if warning:
        return (), (warning,)
    if frontmatter is None:
        return (), ()

    try:
        parsed = yaml.safe_load(frontmatter)
    except yaml.YAMLError as e:
        return (), (f"invalid YAML frontmatter: {e}",)

    if parsed is None:
        return (), ()
    if not isinstance(parsed, dict):
        return (), ("frontmatter must be a mapping",)

    uses = parsed.get("uses")
    if uses is None:
        return (), ()
    if not isinstance(uses, dict):
        return (), ("uses must be a mapping",)

    rows: list[tuple[str, str]] = []
    for field, use_kind in (("schemas", "schema"), ("tables", "table")):
        values = uses.get(field, [])
        if values is None:
            continue
        if not _is_string_list(values):
            return (), (f"uses.{field} must be a list of strings",)
        if field == "tables" and any("." not in value for value in values):
            return (), ("uses.tables entries must be schema-qualified",)
        rows.extend((use_kind, value) for value in values)

    extra = sorted(set(uses) - {"schemas", "tables"})
    if extra:
        return (), ("uses only supports schemas and tables",)
    return tuple(rows), ()


def _frontmatter(content: str) -> tuple[str | None, str | None]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), None
    return None, "frontmatter opening marker has no closing marker"


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)
