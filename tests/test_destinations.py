import unittest
from unittest.mock import patch

from agents_schema.config import ConfigError
from agents_schema.destinations import (
    BigQueryDestination,
    ClickHouseDestination,
    DatabricksDestination,
    SnowflakeDestination,
    _bigquery_credentials_from_secret,
    _clickhouse_connect_kwargs_from_secret,
    _create_table_if_not_exists_sql,
    _databricks_connect_kwargs_from_secret,
    _merge_sql,
    open_destination,
)
from agents_schema.root import ROOT


class DestinationSqlTests(unittest.TestCase):
    def test_snowflake_destination_accepts_explicit_connection_kwargs(self):
        with patch("snowflake.connector.connect") as connect:
            dest = SnowflakeDestination(connect_kwargs={"account": "acct", "user": "user"})

        connect.assert_called_once_with(account="acct", user="user")
        dest.close()

    def test_root_create_table_uses_if_not_exists(self):
        sql = _create_table_if_not_exists_sql(ROOT, "agents")

        self.assertEqual(
            sql,
            "CREATE TABLE IF NOT EXISTS agents.root (\n"
            "    provider VARCHAR NOT NULL,\n"
            "    key VARCHAR NOT NULL,\n"
            "    content TEXT NOT NULL,\n"
            "    PRIMARY KEY (provider, key)\n"
            ")",
        )

    def test_root_merge_upserts_on_provider_and_key(self):
        sql = _merge_sql(ROOT, "agents", 2)

        self.assertIn("MERGE INTO agents.root AS target", sql)
        self.assertIn(
            "USING (SELECT %s AS provider, %s AS key, %s AS content "
            "UNION ALL SELECT %s AS provider, %s AS key, %s AS content) AS source",
            sql,
        )
        self.assertIn("ON target.provider = source.provider AND target.key = source.key", sql)
        self.assertIn("WHEN MATCHED THEN UPDATE SET target.content = source.content", sql)
        self.assertIn(
            "WHEN NOT MATCHED THEN INSERT (provider, key, content) "
            "VALUES (source.provider, source.key, source.content)",
            sql,
        )

    def test_databricks_destination_accepts_explicit_connection_kwargs(self):
        with patch("databricks.sql.connect") as connect:
            dest = DatabricksDestination(
                connect_kwargs={
                    "server_hostname": "dbc-test.cloud.databricks.com",
                    "http_path": "/sql/1.0/warehouses/abc",
                    "catalog": "main",
                    "access_token": "tok",
                }
            )

        connect.assert_called_once_with(
            server_hostname="dbc-test.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            catalog="main",
            access_token="tok",
        )
        dest.close()

    def test_databricks_credentials_accept_public_shape(self):
        kwargs = _databricks_connect_kwargs_from_secret(
            {
                "type": "databricks",
                "host": "dbc-test.cloud.databricks.com",
                "http_path": "/sql/1.0/warehouses/abc",
                "catalog": "main",
                "token": "tok",
            }
        )

        self.assertEqual(
            kwargs,
            {
                "server_hostname": "dbc-test.cloud.databricks.com",
                "http_path": "/sql/1.0/warehouses/abc",
                "catalog": "main",
                "access_token": "tok",
            },
        )

    def test_databricks_credentials_accept_internal_aliases(self):
        kwargs = _databricks_connect_kwargs_from_secret(
            {
                "type": "databricks",
                "serverHostName": "dbc-test.cloud.databricks.com",
                "httpPath": "/sql/1.0/warehouses/abc",
                "catalog": "main",
                "personalAccessToken": "tok",
            }
        )

        self.assertEqual(kwargs["server_hostname"], "dbc-test.cloud.databricks.com")
        self.assertEqual(kwargs["http_path"], "/sql/1.0/warehouses/abc")
        self.assertEqual(kwargs["access_token"], "tok")

    def test_open_destination_supports_databricks(self):
        with patch("agents_schema.destinations.DatabricksDestination") as destination:
            result = open_destination({"warehouse": {"type": "databricks"}})

        self.assertIs(result, destination.return_value)

    def test_clickhouse_credentials_apply_defaults(self):
        kwargs = _clickhouse_connect_kwargs_from_secret(
            {"type": "clickhouse", "host": "abc.clickhouse.cloud"}
        )

        self.assertEqual(
            kwargs,
            {
                "host": "abc.clickhouse.cloud",
                "username": "default",
                "password": "",
                "secure": True,
            },
        )

    def test_clickhouse_credentials_accept_user_alias_port_and_plain_http(self):
        kwargs = _clickhouse_connect_kwargs_from_secret(
            {
                "type": "clickhouse",
                "host": "localhost",
                "username": "bot",
                "password": "pw",
                "port": "8123",
                "secure": False,
            }
        )

        self.assertEqual(kwargs["username"], "bot")
        self.assertEqual(kwargs["port"], 8123)
        self.assertFalse(kwargs["secure"])

    def test_clickhouse_credentials_parse_string_booleans_strictly(self):
        kwargs = _clickhouse_connect_kwargs_from_secret(
            {"type": "clickhouse", "host": "localhost", "password": "pw", "secure": "false"}
        )
        self.assertFalse(kwargs["secure"])

        with self.assertRaises(ConfigError):
            _clickhouse_connect_kwargs_from_secret(
                {"type": "clickhouse", "host": "localhost", "password": "pw", "secure": "maybe"}
            )

        with self.assertRaises(ConfigError):
            _clickhouse_connect_kwargs_from_secret(
                {"type": "clickhouse", "host": "localhost", "password": "pw", "secure": 1}
            )

    def test_clickhouse_credentials_validate_port(self):
        for port in (0, 65536, "not-a-port", 8123.5, True):
            with self.subTest(port=port), self.assertRaises(ConfigError):
                _clickhouse_connect_kwargs_from_secret(
                    {"type": "clickhouse", "host": "localhost", "port": port}
                )

    def test_clickhouse_credentials_require_host(self):
        with self.assertRaises(ConfigError):
            _clickhouse_connect_kwargs_from_secret({"type": "clickhouse", "password": "pw"})

    def test_clickhouse_destination_accepts_explicit_client(self):
        client = object()

        dest = ClickHouseDestination(client=client)

        self.assertIs(dest._client, client)

    def test_open_destination_supports_clickhouse(self):
        with patch("agents_schema.destinations.ClickHouseDestination") as destination:
            result = open_destination({"warehouse": {"type": "clickhouse"}})

        self.assertIs(result, destination.return_value)

    def test_bigquery_credentials_accept_object_shape(self):
        credentials, project_id, location = _bigquery_credentials_from_secret(
            {
                "type": "bigquery",
                "project_id": "analytics-project",
                "location": "US",
                "credentials_json": {
                    "type": "service_account",
                    "private_key": "key",
                    "client_email": "bot@example.com",
                },
            }
        )

        self.assertEqual(project_id, "analytics-project")
        self.assertEqual(location, "US")
        self.assertEqual(credentials["type"], "service_account")
        self.assertEqual(credentials["private_key"], "key")

    def test_bigquery_credentials_accept_json_string(self):
        credentials, project_id, _ = _bigquery_credentials_from_secret(
            {
                "type": "bigquery",
                "project_id": "analytics-project",
                "credentials_json": '{"private_key": "key", "client_email": "bot@example.com"}',
            }
        )

        self.assertEqual(project_id, "analytics-project")
        self.assertEqual(credentials["client_email"], "bot@example.com")

    def test_bigquery_credentials_accept_flattened_service_account_fields(self):
        credentials, project_id, _ = _bigquery_credentials_from_secret(
            {
                "type": "big_query",
                "project_id": "analytics-project",
                "private_key": "key",
                "client_email": "bot@example.com",
            }
        )

        self.assertEqual(project_id, "analytics-project")
        self.assertEqual(credentials["project_id"], "analytics-project")
        self.assertEqual(credentials["private_key"], "key")

    def test_bigquery_destination_accepts_explicit_client(self):
        client = object()

        dest = BigQueryDestination(client=client, project_id="analytics-project")

        self.assertIs(dest._client, client)
        self.assertEqual(dest._project_id, "analytics-project")

    def test_open_destination_supports_bigquery(self):
        with patch("agents_schema.destinations.BigQueryDestination") as destination:
            result = open_destination({"warehouse": {"type": "bigquery"}})

        self.assertIs(result, destination.return_value)

    def test_open_destination_supports_big_query_alias(self):
        with patch("agents_schema.destinations.BigQueryDestination") as destination:
            result = open_destination({"warehouse": {"type": "big_query"}})

        self.assertIs(result, destination.return_value)


if __name__ == "__main__":
    unittest.main()
