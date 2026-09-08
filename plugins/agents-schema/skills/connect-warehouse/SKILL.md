---
name: connect-warehouse
description: Connect an AI coding agent to Snowflake, BigQuery, Databricks, or ClickHouse so it can run SQL. Use when warehouse access is missing, authentication or connection selection is required, or before using a warehouse-data skill such as agents-schema-search.
---

# Connect Warehouse

Identify the warehouse from the user's request, repository configuration, or available clients.
If the warehouse is ambiguous, ask which one they use.

Read exactly one connection guide before proceeding:

- Snowflake: [references/snowflake.md](references/snowflake.md)
- BigQuery: [references/bigquery.md](references/bigquery.md)
- Databricks: [references/databricks.md](references/databricks.md)
- ClickHouse: [references/clickhouse.md](references/clickhouse.md)

Help the user configure the client, select the intended connection, and verify it with the guide's
test query. Do not ask the user to paste credentials or tokens into chat. Stop after connection
verification unless the user also asked to run a query or invoke another skill.
