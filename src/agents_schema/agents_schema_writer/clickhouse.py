from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from agents_schema.config import ConfigError

from .base import AgentsSchemaWriter
from .schema import AGENTS_SCHEMA, Column, TableSchema
from .utils import batched, primary_key_rows

INSERT_BATCH_SIZE = 1000
CLICKHOUSE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# Lightweight DELETEs are applied as a mask immediately visible to subsequent
# SELECTs; setting lightweight_deletes_sync=2 additionally waits for the
# delete to execute on all replicas before returning.
_DELETE_SETTINGS = {"lightweight_deletes_sync": 2}


class ClickHouseAgentsSchemaWriter(AgentsSchemaWriter):
    """Writes agents.* tables to ClickHouse via a clickhouse-connect client.

    ClickHouse-specific mapping decisions:
    - The AGENTS schema maps to a ClickHouse *database* named ``agents``
      (ClickHouse has a two-level ``database.table`` namespace).
    - ClickHouse identifiers are case-sensitive; this writer quotes and creates
      the package's canonical lowercase names.
    - Declared primary keys become the MergeTree ``ORDER BY`` key. ClickHouse
      does not enforce uniqueness, so upserts are implemented as a scoped
      lightweight ``DELETE`` of the incoming keys followed by an ``INSERT``.
    - Row values are never interpolated into SQL text: inserts go through the
      driver's native ``client.insert`` binding and delete predicates bind key
      values as query parameters.
    - ``array`` columns map to ``Array(String)``. ``json`` columns map to the
      native ``JSON`` type on servers that support it (25.3+, where the type is
      production-ready), and fall back to ``String`` holding JSON text on
      older or unidentifiable servers.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        self._json_type: str | None = None
        self._database_verified = False

    def ensure_table(self, table: TableSchema) -> None:
        self._ensure_database()
        self._command(self._create_table_sql("CREATE TABLE IF NOT EXISTS", table))

    def replace_table(self, table: TableSchema) -> None:
        self._ensure_database()
        self._command(self._create_table_sql("CREATE OR REPLACE TABLE", table))

    def _ensure_database(self) -> None:
        if self._database_verified:
            return
        # CREATE DATABASE IF NOT EXISTS still requires the CREATE DATABASE
        # grant when the database already exists, so probe first: the
        # documented least-privilege setup grants the sync user rights only
        # inside an admin-created agents database.
        exists = self._client.command(
            "SELECT count() FROM system.databases WHERE name = {db:String}",
            parameters={"db": AGENTS_SCHEMA},
        )
        if not int(exists or 0):
            self._command(f"CREATE DATABASE IF NOT EXISTS {self._identifier(AGENTS_SCHEMA)}")
        self._database_verified = True

    def upsert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        if not table.primary_key:
            raise ConfigError("upsert requires a table primary key")
        rows = list(rows)
        if not rows:
            return
        self.ensure_table(table)
        self._delete_matching_keys(table, table.primary_key, primary_key_rows(table, rows))
        self.insert_rows(table, rows)

    def insert_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        rows = list(rows)
        if not rows:
            return
        self._validate_identifiers(table)
        column_names = [column.name for column in table.columns]
        data = [self._row_values(table, row) for row in rows]
        for batch in batched(data, INSERT_BATCH_SIZE):
            self._client.insert(
                table.base_name,
                list(batch),
                column_names=column_names,
                database=AGENTS_SCHEMA,
            )

    def delete_rows(
        self,
        table: TableSchema,
        key_columns: tuple[str, ...],
        rows: Iterable[tuple[Any, ...]],
    ) -> None:
        if not key_columns:
            raise ConfigError("delete requires at least one key column")
        key_rows = list(rows)
        if not key_rows:
            return
        self.ensure_table(table)
        self._delete_matching_keys(table, key_columns, key_rows)

    def reconcile_rows(self, table: TableSchema, rows: Iterable[tuple[Any, ...]]) -> None:
        rows = list(rows)
        self.ensure_table(table)
        self.upsert_rows(table, rows)
        self._delete_absent_rows(table, primary_key_rows(table, rows))

    def close(self) -> None:
        self._client.close()

    def _command(
        self,
        sql: str,
        settings: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self._client.command(sql, settings=settings, parameters=parameters)

    def _delete_matching_keys(
        self,
        table: TableSchema,
        key_columns: tuple[str, ...],
        key_rows: list[tuple[Any, ...]],
    ) -> None:
        for batch in batched(key_rows, INSERT_BATCH_SIZE):
            predicate, parameters = self._key_predicate(key_columns, list(batch))
            self._command(
                f"DELETE FROM {self._table_ref(table)} WHERE {predicate}",
                settings=_DELETE_SETTINGS,
                parameters=parameters,
            )

    def _delete_absent_rows(self, table: TableSchema, key_rows: list[tuple[Any, ...]]) -> None:
        if not key_rows:
            self._command(f"TRUNCATE TABLE {self._table_ref(table)}")
            return
        predicate, parameters = self._key_predicate(table.primary_key, key_rows)
        self._command(
            f"DELETE FROM {self._table_ref(table)} WHERE NOT ({predicate})",
            settings=_DELETE_SETTINGS,
            parameters=parameters,
        )

    def _key_predicate(
        self, key_columns: tuple[str, ...], key_rows: list[tuple[Any, ...]]
    ) -> tuple[str, dict[str, Any]]:
        """Build a parameterized ``IN`` predicate; key values are never inlined."""
        if len(key_columns) == 1:
            column = self._identifier(key_columns[0])
            values = [_key_text(row[0]) for row in key_rows]
            return f"{column} IN {{keys:Array(String)}}", {"keys": values}
        columns = "(" + ", ".join(self._identifier(column) for column in key_columns) + ")"
        tuple_type = ", ".join(["String"] * len(key_columns))
        values = [tuple(_key_text(value) for value in row) for row in key_rows]
        return f"{columns} IN {{keys:Array(Tuple({tuple_type}))}}", {"keys": values}

    def _row_values(self, table: TableSchema, row: tuple[Any, ...]) -> list[Any]:
        values: list[Any] = []
        for index, (column, value) in enumerate(zip(table.columns, row, strict=True)):
            if index in table.array_indexes:
                # Array-kind values are not always lists: OSI ai_context is a
                # string OR an object (VARIANT on Snowflake). A non-list value
                # becomes a single element so nothing is iterated into keys or
                # characters; non-string elements are stored as JSON text,
                # mirroring the JSON shape other destinations keep in VARIANT.
                if value is None:
                    items = []
                elif isinstance(value, (list, tuple)):
                    items = list(value)
                else:
                    items = [value]
                values.append(
                    [item if isinstance(item, str) else json.dumps(item) for item in items]
                )
            elif index in table.json_indexes:
                values.append(json.dumps({} if value is None else value))
            elif column.kind == "boolean":
                values.append(None if value is None else bool(value))
            else:
                values.append(None if value is None else str(value))
        return values

    def _create_table_sql(self, prefix: str, table: TableSchema) -> str:
        definitions = ", ".join(
            f"{self._identifier(column.name)} {_clickhouse_type(column, self._resolve_json_type())}"
            for column in table.columns
        )
        order_by = (
            "(" + ", ".join(self._identifier(column) for column in table.primary_key) + ")"
            if table.primary_key
            else "tuple()"
        )
        return (
            f"{prefix} {self._table_ref(table)} ({definitions}) "
            f"ENGINE = MergeTree ORDER BY {order_by}"
        )

    def _table_ref(self, table: TableSchema) -> str:
        return f"{self._identifier(AGENTS_SCHEMA)}.{self._identifier(table.base_name)}"

    def _validate_identifiers(self, table: TableSchema) -> None:
        self._identifier(table.base_name)
        for column in table.columns:
            self._identifier(column.name)

    def _identifier(self, identifier: str) -> str:
        if not CLICKHOUSE_IDENTIFIER_RE.fullmatch(identifier):
            raise ConfigError(f"expected a simple ClickHouse identifier: {identifier}")
        return f"`{identifier}`"

    def _resolve_json_type(self) -> str:
        """Use the native JSON type on 25.3+, else String holding JSON text."""
        if self._json_type is None:
            self._json_type = "JSON" if _supports_json_type(self._client) else "String"
        return self._json_type


def _supports_json_type(client: Any) -> bool:
    """Fail closed: only use the native JSON type on a confirmed 25.3+ server."""
    version = getattr(client, "server_version", None)
    if not version:
        return False
    parts = str(version).split(".")
    try:
        major, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return False
    return (major, minor) >= (25, 3)


def _clickhouse_type(column: Column, json_type: str) -> str:
    if column.kind == "array":
        return "Array(String)"
    if column.kind == "json":
        # Nullable(JSON) is not supported; missing values are written as {}.
        return json_type
    if column.kind == "boolean":
        return "Nullable(Bool)" if column.nullable else "Bool"
    if column.kind in {"text", "varchar"}:
        return "Nullable(String)" if column.nullable else "String"
    raise ValueError(f"unsupported column kind: {column.kind}")


def _key_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)
