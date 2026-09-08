from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from agents_schema.agents_schema_writer import (
    BigQueryAgentsSchemaWriter,
    ClickHouseAgentsSchemaWriter,
    DatabricksAgentsSchemaWriter,
)
from agents_schema.dbt import DBT_MODEL


class BigQueryAgentsSchemaWriterTests(unittest.TestCase):
    def test_upsert_rows_loads_staging_and_merges(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p")

            writer.upsert_rows(
                DBT_MODEL,
                [
                    ("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], {}),
                    (
                        "model.pkg.customers",
                        "customers",
                        None,
                        "analytics",
                        "view",
                        "desc",
                        "models/customers.sql",
                        ["mart"],
                        {},
                    ),
                ],
            )

        load_calls = [call for call in calls if call[0] == "load"]
        query_calls = [call for call in calls if call[0] == "query"]
        self.assertEqual(len(load_calls), 1)
        self.assertEqual(len(load_calls[0][1]), 2)
        self.assertEqual(len(query_calls), 1)
        query_sql = query_calls[0][1]
        self.assertIn("MERGE `p.agents.dbt_model` AS target", query_sql)
        self.assertIn("USING `p.agents._staging_dbt_model_", query_sql)
        self.assertIn("WHEN MATCHED THEN UPDATE SET", query_sql)
        self.assertIn("WHEN NOT MATCHED THEN INSERT", query_sql)
        self.assertTrue(any(call[0] == "delete_table" and call[1].startswith("p.agents._staging_dbt_model_") for call in calls))

    def test_reconcile_rows_deletes_stale_rows(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p")

            writer.reconcile_rows(
                DBT_MODEL,
                [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], {})],
            )

        query_sql = next(call[1] for call in calls if call[0] == "query")
        self.assertIn("MERGE `p.agents.dbt_model` AS target", query_sql)
        self.assertIn("WHEN NOT MATCHED BY SOURCE THEN DELETE", query_sql)

    def test_reconcile_rows_deletes_all_when_empty(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p")

            writer.reconcile_rows(DBT_MODEL, [])

        self.assertIn(("query", "DELETE FROM `p.agents.dbt_model` WHERE TRUE", None), calls)

    def test_array_columns_are_repeated_string_fields(self):
        calls = []
        with _fake_bigquery_module():
            writer = BigQueryAgentsSchemaWriter(_FakeBigQueryClient(calls), "p", location="US")

            writer.ensure_table(DBT_MODEL)

        create_table_call = next(call for call in calls if call[0] == "create_table")
        table = create_table_call[1]
        tag_field = next(field for field in table.schema if field.args[0] == "tags")
        self.assertEqual(tag_field.args, ("tags", "STRING"))
        self.assertEqual(tag_field.kwargs["mode"], "REPEATED")
        meta_field = next(field for field in table.schema if field.args[0] == "meta")
        self.assertEqual(meta_field.args, ("meta", "JSON"))
        create_dataset_call = next(call for call in calls if call[0] == "create_dataset")
        self.assertEqual(create_dataset_call[1].location, "US")


class DatabricksAgentsSchemaWriterTests(unittest.TestCase):
    def test_upsert_rows_uses_merge_and_native_markers(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.upsert_rows(
            DBT_MODEL,
            [
                ("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], {}),
                ("model.pkg.customers", "customers", None, "analytics", "view", "desc", "models/customers.sql", ["mart"], {}),
            ],
        )

        merge_calls = [call for call in calls if call[0].startswith("MERGE")]
        self.assertEqual(len(merge_calls), 1)
        merge_sql, params = merge_calls[0]
        self.assertIn("MERGE INTO `agents`.`dbt_model` AS target", merge_sql)
        self.assertEqual(merge_sql.count("SELECT ? AS"), 2)
        self.assertIn("from_json(?, 'array<string>') AS `tags`", merge_sql)
        self.assertIn("parse_json(?) AS `meta`", merge_sql)
        self.assertIn("target.`unique_id` = source.`unique_id`", merge_sql)
        self.assertIn("WHEN MATCHED THEN UPDATE SET", merge_sql)
        self.assertNotIn("%s", merge_sql)
        self.assertEqual(
            params,
            [
                "model.pkg.orders",
                "orders",
                None,
                "analytics",
                "table",
                "",
                "models/orders.sql",
                "[]",
                "{}",
                "model.pkg.customers",
                "customers",
                None,
                "analytics",
                "view",
                "desc",
                "models/customers.sql",
                '["mart"]',
                "{}",
            ],
        )

    def test_insert_rows_batches_json_arrays(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.insert_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", ["finance"], {})],
        )

        self.assertEqual(len(calls), 1)
        insert_sql, params = calls[0]
        self.assertIn("INSERT INTO `agents`.`dbt_model`", insert_sql)
        self.assertIn("from_json(?, 'array<string>')", insert_sql)
        self.assertEqual(params[-2], '["finance"]')
        self.assertEqual(params[-1], '{}')

    def test_reconcile_rows_deletes_absent_primary_keys(self):
        calls = []
        writer = DatabricksAgentsSchemaWriter(_fake_connection(calls))

        writer.reconcile_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], {})],
        )

        delete_calls = [call for call in calls if call[0].startswith("DELETE FROM")]
        self.assertEqual(len(delete_calls), 1)
        delete_sql, params = delete_calls[0]
        self.assertIn("DELETE FROM `agents`.`dbt_model` AS target", delete_sql)
        self.assertIn("target.`unique_id` = source.`unique_id`", delete_sql)
        self.assertEqual(params, ["model.pkg.orders"])


class ClickHouseAgentsSchemaWriterTests(unittest.TestCase):
    def test_replace_table_creates_mergetree_ordered_by_primary_key(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))

        writer.replace_table(DBT_MODEL)

        sqls = [call[1] for call in calls if call[0] == "command"]
        self.assertTrue(sqls[0].startswith("SELECT count() FROM system.databases"))
        self.assertEqual(sqls[1], "CREATE DATABASE IF NOT EXISTS `agents`")
        create_sql = sqls[2]
        self.assertIn("CREATE OR REPLACE TABLE `agents`.`dbt_model`", create_sql)
        self.assertIn("`unique_id` String", create_sql)
        self.assertIn("`description` Nullable(String)", create_sql)
        self.assertIn("`tags` Array(String)", create_sql)
        self.assertIn("`meta` JSON", create_sql)
        self.assertIn("ENGINE = MergeTree ORDER BY (`unique_id`)", create_sql)

    def test_upsert_rows_deletes_incoming_keys_then_inserts(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))

        writer.upsert_rows(
            DBT_MODEL,
            [
                ("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], {}),
                ("model.pkg.customers", "customers", None, "analytics", "view", "desc", "models/customers.sql", ["mart"], {}),
            ],
        )

        delete_calls = [call for call in calls if call[0] == "command" and call[1].startswith("DELETE")]
        self.assertEqual(len(delete_calls), 1)
        _, delete_sql, delete_settings, delete_params = delete_calls[0]
        self.assertIn("DELETE FROM `agents`.`dbt_model`", delete_sql)
        self.assertIn("`unique_id` IN {keys:Array(String)}", delete_sql)
        self.assertEqual(delete_params, {"keys": ["model.pkg.orders", "model.pkg.customers"]})
        self.assertEqual(delete_settings, {"lightweight_deletes_sync": 2})

        insert_calls = [call for call in calls if call[0] == "insert"]
        self.assertEqual(len(insert_calls), 1)
        _, table, data, column_names, database = insert_calls[0]
        self.assertEqual((database, table), ("agents", "dbt_model"))
        self.assertEqual(column_names[0], "unique_id")
        self.assertEqual(data[1][7], ["mart"])
        self.assertEqual(data[0][8], "{}")
        self.assertIsNone(data[0][2])
        self.assertGreater(calls.index(insert_calls[0]), calls.index(delete_calls[0]))

    def test_insert_rows_passes_values_as_data_not_sql(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))
        tricky = "it's a \\ test with {id:UInt64}\nand a newline"

        writer.insert_rows(
            DBT_MODEL,
            [("model.pkg.o", "o", None, "analytics", "table", tricky, "models/o.sql", [], {"a": 1})],
        )

        insert_calls = [call for call in calls if call[0] == "insert"]
        self.assertEqual(len(insert_calls), 1)
        _, _, data, _, _ = insert_calls[0]
        self.assertEqual(data[0][5], tricky)
        self.assertEqual(data[0][8], '{"a": 1}')

    def test_reconcile_rows_deletes_absent_primary_keys(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))

        writer.reconcile_rows(
            DBT_MODEL,
            [("model.pkg.orders", "orders", None, "analytics", "table", "", "models/orders.sql", [], {})],
        )

        absent_deletes = [call for call in calls if call[0] == "command" and "NOT (" in call[1]]
        self.assertEqual(len(absent_deletes), 1)
        _, sql, _, params = absent_deletes[0]
        self.assertIn("NOT (`unique_id` IN {keys:Array(String)})", sql)
        self.assertEqual(params, {"keys": ["model.pkg.orders"]})

    def test_reconcile_rows_truncates_when_empty(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))

        writer.reconcile_rows(DBT_MODEL, [])

        self.assertIn(("command", "TRUNCATE TABLE `agents`.`dbt_model`", None, None), calls)

    def test_multi_column_key_deletes_use_tuples(self):
        from agents_schema.root import ROOT

        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))

        writer.upsert_rows(ROOT, [("dbt", "overview", "# dbt")])

        delete = next(call for call in calls if call[0] == "command" and call[1].startswith("DELETE"))
        self.assertIn("(`provider`, `key`) IN {keys:Array(Tuple(String, String))}", delete[1])
        self.assertEqual(delete[3], {"keys": [("dbt", "overview")]})

    def test_json_columns_fall_back_to_string_before_25_3(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls, server_version="24.8.1.1"))

        writer.replace_table(DBT_MODEL)

        create_sql = next(call[1] for call in calls if "CREATE OR REPLACE TABLE" in call[1])
        self.assertIn("`meta` String", create_sql)
        self.assertNotIn("`meta` JSON", create_sql)

    def test_json_columns_fall_back_to_string_when_version_unknown(self):
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls, server_version=None))

        writer.replace_table(DBT_MODEL)

        create_sql = next(call[1] for call in calls if "CREATE OR REPLACE TABLE" in call[1])
        self.assertIn("`meta` String", create_sql)
        self.assertNotIn("`meta` JSON", create_sql)

    def test_existing_database_is_not_recreated(self):
        # CREATE DATABASE IF NOT EXISTS still requires the CREATE DATABASE
        # grant when the database exists; the documented least-privilege user
        # must be able to sync into an admin-created agents database.
        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls, database_exists=True))

        writer.replace_table(DBT_MODEL)
        writer.ensure_table(DBT_MODEL)

        sqls = [call[1] for call in calls if call[0] == "command"]
        self.assertFalse(any(sql.startswith("CREATE DATABASE") for sql in sqls))
        probes = [sql for sql in sqls if sql.startswith("SELECT count() FROM system.databases")]
        self.assertEqual(len(probes), 1)

    def test_array_values_preserve_object_and_string_shapes(self):
        # OSI ai_context is a string OR an object (VARIANT on Snowflake); a
        # non-list value must become a single element, never be iterated into
        # dict keys or characters.
        from agents_schema.osi import OSI_MODEL

        calls = []
        writer = ClickHouseAgentsSchemaWriter(_FakeClickHouseClient(calls))
        structured = {"instructions": "Use amount_usd not amount for MRR.", "synonyms": ["mrr"]}

        writer.insert_rows(
            OSI_MODEL,
            [
                ("revenue", "1.0", "desc", ["mrr"], structured, None),
                ("orders", "1.0", "desc", [], "prefer the signed-in customer grain", None),
            ],
        )

        insert_calls = [call for call in calls if call[0] == "insert"]
        self.assertEqual(len(insert_calls), 1)
        data = insert_calls[0][2]
        self.assertEqual(
            data[0][4], ['{"instructions": "Use amount_usd not amount for MRR.", "synonyms": ["mrr"]}']
        )
        self.assertEqual(data[1][4], ["prefer the signed-in customer grain"])
        self.assertEqual(data[1][5], [])


class _FakeClickHouseClient:
    def __init__(self, calls, server_version="26.1.1.1", database_exists=False):
        self.calls = calls
        self.database_exists = database_exists
        if server_version is not None:
            self.server_version = server_version

    def command(self, sql, settings=None, parameters=None):
        self.calls.append(("command", sql, settings, parameters))
        if sql.startswith("SELECT count() FROM system.databases"):
            return 1 if self.database_exists else 0
        return None

    def insert(self, table, data, column_names=None, database=None):
        self.calls.append(("insert", table, data, column_names, database))

    def close(self):
        pass


def _fake_connection(calls):
    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append((sql, params))

    @contextmanager
    def fake_cursor():
        yield FakeCursor()

    return SimpleNamespace(cursor=fake_cursor, close=lambda: None)


class _Job:
    def result(self):
        return None


class _FakeBigQueryClient:
    def __init__(self, calls):
        self.calls = calls

    def create_dataset(self, dataset, exists_ok=False):
        self.calls.append(("create_dataset", dataset, exists_ok))

    def create_table(self, table, exists_ok=False):
        self.calls.append(("create_table", table, exists_ok))

    def delete_table(self, table_ref, not_found_ok=False):
        self.calls.append(("delete_table", table_ref, not_found_ok))

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self.calls.append(("load", rows, table_ref, job_config))
        return _Job()

    def query(self, sql, job_config=None):
        self.calls.append(("query", sql, job_config))
        return _Job()


def _fake_bigquery_module():
    fake_google = ModuleType("google")
    fake_cloud = ModuleType("google.cloud")
    fake_bigquery = ModuleType("google.cloud.bigquery")

    class WriteDisposition:
        WRITE_APPEND = "WRITE_APPEND"
        WRITE_TRUNCATE = "WRITE_TRUNCATE"

    class LoadJobConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class QueryJobConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class ScalarQueryParameter:
        def __init__(self, *args):
            self.args = args

    class SchemaField:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Dataset:
        def __init__(self, ref):
            self.ref = ref
            self.location = None

    class Table:
        def __init__(self, ref, schema=None):
            self.ref = ref
            self.schema = schema

    fake_bigquery.WriteDisposition = WriteDisposition
    fake_bigquery.LoadJobConfig = LoadJobConfig
    fake_bigquery.QueryJobConfig = QueryJobConfig
    fake_bigquery.ScalarQueryParameter = ScalarQueryParameter
    fake_bigquery.SchemaField = SchemaField
    fake_bigquery.Dataset = Dataset
    fake_bigquery.Table = Table
    fake_cloud.bigquery = fake_bigquery
    fake_google.cloud = fake_cloud
    return patch.dict(
        sys.modules,
        {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
        },
    )


if __name__ == "__main__":
    unittest.main()
