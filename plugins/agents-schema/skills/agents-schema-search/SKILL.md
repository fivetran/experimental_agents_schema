---
name: agents-schema-search
description: >
  Use when answering questions about data in a warehouse (BigQuery, Snowflake, etc.) and you have direct SQL access (CLI, driver, or console). Discover metadata and run knowledge search through the warehouse-native AGENTS schema instead of INFORMATION_SCHEMA.
---

# Answering warehouse-data questions via the AGENTS schema

Before answering a warehouse-data question, read the warehouse AGENTS schema.

AGENTS.ROOT is the entry point for the warehouse-native Agents Schema. It tells
AI agents which providers have published metadata and how to use their
provider-specific tables.

Use AGENTS as the warehouse metadata and discovery surface. Treat it like an
agent-oriented alternative to INFORMATION_SCHEMA: inspect AGENTS.ROOT and the
provider-specific AGENTS.* tables instead of querying INFORMATION_SCHEMA
directly. Only fall back to INFORMATION_SCHEMA when the AGENTS content
explicitly says to verify live metadata, or when required metadata is missing
from AGENTS.

Use your connection's SQL dialect (e.g. GoogleSQL on BigQuery), and quote
schema and table identifiers using that dialect. Run read-only SELECT
statements only.

Required first query:

```sql
SELECT * FROM agents.root ORDER BY provider, key;
```

These are the canonical physical names created by the package. Lowercase is
required on case-sensitive destinations such as ClickHouse and BigQuery and is
also accepted by Snowflake and Databricks. Use lowercase for provider tables as
well, for example `agents.dbt_model`.

Then follow the provider guidance returned in the `content` column.

If no rows are returned, or the AGENTS schema or the AGENTS.ROOT table is not
found, tell the user that their AGENTS schema is not set up yet.
