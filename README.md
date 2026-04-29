# Agents Schema

**A standard for communicating metadata to agents in a lakehouse.**

The Agents Schema is to lakehouses what `AGENTS.md` is to code repositories: a well-known location where tools, agents, and humans can discover what data exists, who owns it, and how to use it responsibly.

![Agents Schema overview](assets/agents-schema-overview.png)

---

## Motivation

Agents operating over a lakehouse need context that isn't captured in table schemas alone: what a table is for, who maintains it, what transformations produced it, what it costs to query, and how it relates to other tables. Today this information lives in wikis, Slack threads, and tribal knowledge. The Agents Schema puts it in the warehouse itself, where agents can find it without leaving the query interface.

---

## What This Is For

The Agents Schema is primarily a discovery and orientation layer for agents working from inside a lakehouse or warehouse query surface.

Its main use cases are:
- helping agents discover what data exists, who owns it, and how it should be interpreted
- surfacing operational and semantic context close to the data itself
- providing a standard in-warehouse place for metadata from multiple systems to coexist
- enabling portable agent and tool behavior across warehouses without bespoke integrations for every provider

In practice, this means an agent should be able to connect to a warehouse, inspect the `AGENTS` schema, and quickly answer questions like:
- what curated tables exist versus raw ingested tables?
- which system populated this schema?
- what dbt model or semantic object represents this dataset?
- is this source stale or unhealthy?
- who owns this data product?

Well-known extensions are also a mechanism for tools to discover specific metadata they care about. For example:
- a BI tool could look specifically for dbt semantic-layer tables such as `AGENTS.DBT_SEMANTIC_MODEL`, `AGENTS.DBT_METRIC`, or related tables
- an observability tool could look for freshness or lineage metadata from a specific provider
- a generic agent runtime could use `AGENTS.ROOT` to discover which providers are present before deciding what else to query

The point is interoperability at the warehouse boundary: enough standardization that generic agents and downstream tools can discover useful context without direct access to every upstream system.

An important property of the Agents Schema is that it is self-documenting. The schema is meant to describe itself from inside the warehouse:
- `AGENTS.ROOT` tells a reader which providers are present
- the descriptions in `AGENTS.ROOT` explain what provider-contributed tables exist and how to interpret them
- a consumer can discover useful metadata by querying the warehouse alone, without prior vendor-specific assumptions

Well-known extensions are an optimization on top of that default discovery flow, not a replacement for it. A tool may choose to look directly for a stable, well-known table shape such as a dbt semantic-layer extension, but it does not have to. The baseline contract is still that the schema can be explored and understood through `AGENTS.ROOT`.

---

## What This Is Not For

The Agents Schema is not intended to replace specialized systems, source-native metadata APIs, or development-time tooling.

In particular, it is not:
- a full replacement for dbt artifacts, dbt Cloud APIs, or repository-native metadata parsing
- a substitute for source-control-aware tooling that operates on project files
- the canonical execution interface for vendor-specific platforms
- a complete semantic layer, catalog, or observability product by itself
- a requirement that every tool consume metadata from the warehouse instead of from primary sources

Specialized tools should still build their own context when they need deeper, fresher, or source-native representations.

For example:
- a dbt MCP server meant to help coding agents work on a dbt repository should build its context from the repository itself: model SQL files, YAML properties files, macros, `dbt_project.yml`, and dbt artifacts
- that server should not treat the `AGENTS` schema as its primary source of truth for authoring, refactoring, or validating dbt code
- similarly, a catalog, lineage engine, or observability platform may ingest the Agents Schema, but will often maintain a richer internal model built from APIs, repository scans, logs, or event streams

The Agents Schema is therefore best understood as:
- a shared, queryable metadata surface inside the lakehouse
- a lowest-common-denominator interoperability layer
- a convenient place for agents and tools to discover context when working from the data plane

It is not:
- the only metadata surface in the ecosystem
- the deepest possible representation of any provider's semantics
- a reason to stop building specialized tools with source-native context models

---

## Design Boundary

The boundary is:
- if the consumer starts from the warehouse and needs context about data that already exists there, the Agents Schema is a good fit
- if the consumer starts from a source system or codebase and needs full-fidelity authoring or operational context, it should usually use that system's native artifacts and APIs directly

This is especially important for coding and development workflows. A tool helping an agent edit a dbt repository should use dbt's source files and artifacts directly. A tool helping an agent understand a warehouse it can query should be able to benefit from the Agents Schema.

---

## Comparison to Related Concepts

### Compared to `AGENTS.md`

The analogy to `AGENTS.md` is useful, but the setting is different.

- `AGENTS.md` is for code repositories; the Agents Schema is for warehouses and lakehouses
- `AGENTS.md` is typically curated by developers in a repo; the Agents Schema is expected to be written to by multiple providers that share the same warehouse
- `AGENTS.ROOT.description` is intentionally unstructured markdown, similar to `AGENTS.md`
- beyond `AGENTS.ROOT`, the rest of the Agents Schema will often be more structured, because provider-contributed tables are meant to support machine-readable discovery and joins

### Compared to `information_schema`

The closest existing database analogy is `information_schema`.

- both are meant to be discoverable from inside the database itself
- the Agents Schema is self-documenting through `AGENTS.ROOT`, in the same spirit that `information_schema` exposes metadata from within the system
- the main difference is extensibility: `information_schema` is a strong idea, but it is largely fixed by the warehouse provider and not designed as a shared extension surface for many metadata producers
- you can think of `information_schema` as a pre-existing metadata surface from a single provider, while the Agents Schema allows many providers to effectively publish and share their own `information_schema`-like context in one place

### Compared to MCP Servers

MCP servers and the Agents Schema solve related but different problems.

- the Agents Schema does not require separate authentication or a separate service boundary; it relies on the database access that providers and consumers already share
- its scope is narrower: it provides context, but it is not an action interface
- an MCP server can expose tools that take action, orchestrate workflows, or wrap external systems; the Agents Schema only publishes metadata inside the warehouse
- specialized MCP servers are likely to be common consumers of the Agents Schema
- those servers may cache metadata from the Agents Schema, or special-case known providers and well-known extensions when they want a richer or faster consumer experience

## Core: The `AGENTS` Schema

All Agents Schema tables live in a schema named `AGENTS`. The schema name is fixed as `AGENTS`. This schema must be created by whoever administers the lakehouse. Write access should be limited to providers, read access should be granted as broadly as possible. Providers should not place highly sensitive information in the AGENTS schema.

---

## `AGENTS.ROOT`

The single entry point for all metadata. Every provider that contributes metadata registers itself here.

`AGENTS.ROOT` is what makes the Agents Schema self-documenting. A generic consumer should be able to start here, learn which providers have published metadata, and read descriptions of the tables and conventions those providers expose.

```sql
CREATE TABLE AGENTS.ROOT (
  provider    VARCHAR NOT NULL,  -- namespace, e.g. 'fivetran', 'dbt', 'acme_corp'
  key         VARCHAR NOT NULL,  -- provider-defined section identifier
  description TEXT    NOT NULL,  -- markdown text describing this entry
  PRIMARY KEY (provider, key)
);
```

### Columns

| Column | Description |
|---|---|
| `provider` | A short, lowercase identifier for the metadata contributor. Typically a vendor name (`fivetran`, `dbt`) or an internal team name (`acme_data_platform`). Must match the prefix used in any `AGENTS.{PROVIDER}_*` tables contributed by this provider. |
| `key` | An arbitrary string chosen by the provider to organize their description into sections. Examples: `overview`, `connectors`, `lineage`, `costs`. Unique within a provider. |
| `description` | A markdown blob. May describe the provider, explain an extension table, document conventions, or provide any context useful to an agent or human reader. Taken together, these rows document the rest of the schema. |

### Example rows

```
provider   key        description
---------  ---------  ------------------------------------------------
fivetran   overview   # Fivetran\nFivetran syncs data from SaaS sources...
fivetran   schema     See AGENTS.FIVETRAN_CONNECTOR and AGENTS.FIVETRAN_TABLE...
dbt        overview   # dbt\nTransformation layer. See AGENTS.DBT_MODEL...
dbt        lineage    Column-level lineage available in AGENTS.DBT_COLUMN_LINEAGE...
acme_corp  costs      # Query Costs\nSee AGENTS.ACME_CORP_TABLE_COSTS...
```

---

## Cross-Provider Association

Agentic systems often need to attach context to heterogeneous assets: a model, a column, a lineage edge, a connector, a dashboard, or a provider-specific object that does not exist yet. Providers may also want to relate their own rows to arbitrary rows from other providers without forcing every future asset type into the core schema. This section defines a small common projection for those polymorphic associations while keeping provider tables relational and provider-specific.

Every provider table must declare a primary key. The primary key may be a single column or a composite key, but it must be explicit in the table definition so consumers and optional helper functions can identify rows without guessing. For example, `AGENTS.DBT_MODEL.unique_id` remains the primary key for dbt models, and `AGENTS.DBT_DEPENDENCY` keeps its composite `(upstream_id, downstream_id)` primary key.

When an implementation wants polymorphic attachments, it may expose an `AGENTS.ENTITY` view that projects selected provider rows onto a minimal common shape:

```sql
CREATE VIEW AGENTS.ENTITY AS
SELECT 'AGENTS.DBT_MODEL' AS target_table, unique_id AS target_id
FROM AGENTS.DBT_MODEL
UNION ALL
SELECT 'AGENTS.DBT_COLUMN' AS target_table, model_unique_id || ':' || column_name AS target_id
FROM AGENTS.DBT_COLUMN
UNION ALL
SELECT 'AGENTS.DBT_DEPENDENCY' AS target_table, upstream_id || ':' || downstream_id AS target_id
FROM AGENTS.DBT_DEPENDENCY
UNION ALL
SELECT 'AGENTS.FIVETRAN_CONNECTOR' AS target_table, connector_id AS target_id
FROM AGENTS.FIVETRAN_CONNECTOR;
```

`target_id` is only meaningful together with `target_table`. For single-column keys, it can be the primary key value. For composite keys, the view can use a simple concatenation convention owned by that view, such as `upstream_id || ':' || downstream_id`.

This view is intentionally schema-specific. It can be installed as a dbt model, an `on-run-end` hook, or a migration maintained with the provider schemas. It provides a common lookup surface, but it does not make SQL dynamically dispatch into arbitrary provider tables. Queries that need provider-specific columns still need provider-specific SQL or generated SQL.

Implementations may also install a resolver helper that turns a table name and primary-key values into the `target_id` format used by `AGENTS.ENTITY`. A resolver is optional ergonomics: it can rely on the primary keys declared by the provider tables, but it should not be treated as a dynamic join mechanism.

For example, an implementation could expose a resolver function or macro with this contract:

```sql
-- Single-column key
AGENTS.RESOLVE_ID(
  'AGENTS.DBT_MODEL',
  'model.analytics.fct_revenue'
)
-- returns: 'model.analytics.fct_revenue'

-- Composite key, arguments in primary-key order
AGENTS.RESOLVE_ID(
  'AGENTS.DBT_DEPENDENCY',
  'source.my_project.fivetran_salesforce.account',
  'model.analytics.fct_revenue'
)
-- returns: 'source.my_project.fivetran_salesforce.account:model.analytics.fct_revenue'
```

The resolver does not hide the target table or join to it. It only centralizes the string format used for `target_id`, so writers do not hand-concatenate composite keys differently in different places.

This is enough to support polymorphic extension tables without putting those tables in the core spec. The following `AGENTS.MEMORY` tables are an illustrative example, not a required part of this specification. They show how an implementation could associate one piece of context with multiple rows by storing its body once and linking it to `(target_table, target_id)` pairs:

```sql
CREATE TABLE AGENTS.MEMORY (
  memory_id   VARCHAR NOT NULL PRIMARY KEY,
  memory_type VARCHAR NOT NULL, -- 'note', 'observation', 'warning', 'decision'
  content     TEXT NOT NULL,
  author      VARCHAR,
  confidence  FLOAT,
  evidence    VARIANT,
  created_at  TIMESTAMP
);

CREATE TABLE AGENTS.MEMORY_TARGET (
  memory_id    VARCHAR NOT NULL,
  target_table VARCHAR NOT NULL,
  target_id    VARCHAR NOT NULL,
  target_role  VARCHAR, -- 'subject', 'column', 'upstream', 'downstream', etc.
  PRIMARY KEY (memory_id, target_table, target_id)
);
```

The target rows can live in completely different provider tables. One memory can refer to a dbt model, one of its columns, a lineage edge, and an upstream Fivetran connector:

```sql
INSERT INTO AGENTS.MEMORY
  (memory_id, memory_type, content, author, confidence, created_at)
VALUES
  (
    'mem_001',
    'observation',
    'Revenue is reported in USD, depends on the Salesforce connector, and excludes refunds before 2023-Q1.',
    'profiler-agent',
    0.82,
    CURRENT_TIMESTAMP
  );

INSERT INTO AGENTS.MEMORY_TARGET
  (memory_id, target_table, target_id, target_role)
VALUES
  (
    'mem_001',
    'AGENTS.DBT_MODEL',
    AGENTS.RESOLVE_ID('AGENTS.DBT_MODEL', 'model.analytics.fct_revenue'),
    'subject'
  ),
  (
    'mem_001',
    'AGENTS.DBT_COLUMN',
    AGENTS.RESOLVE_ID('AGENTS.DBT_COLUMN', 'model.analytics.fct_revenue', 'revenue_usd'),
    'column'
  ),
  (
    'mem_001',
    'AGENTS.DBT_DEPENDENCY',
    AGENTS.RESOLVE_ID(
      'AGENTS.DBT_DEPENDENCY',
      'source.my_project.fivetran_salesforce.account',
      'model.analytics.fct_revenue'
    ),
    'lineage_edge'
  ),
  (
    'mem_001',
    'AGENTS.FIVETRAN_CONNECTOR',
    AGENTS.RESOLVE_ID('AGENTS.FIVETRAN_CONNECTOR', 'salesforce_prod'),
    'upstream'
  );
```

The write path does not need a separate memory table per entity type. The `(target_table, target_id)` pair is the polymorphic reference, and the same memory can attach to heterogeneous targets.

With that view, reads work from either direction. To resolve every object associated with a memory:

```sql
SELECT
  mt.target_role,
  mt.target_table,
  mt.target_id
FROM AGENTS.MEMORY_TARGET mt
JOIN AGENTS.ENTITY e
  ON e.target_table = mt.target_table
 AND e.target_id = mt.target_id
WHERE mt.memory_id = 'mem_001'
ORDER BY mt.target_role, mt.target_table, mt.target_id;
```

To find every memory attached to a specific provider row, use that row's normal key encoded the same way as `AGENTS.ENTITY`:

```sql
SELECT
  m.memory_id,
  m.memory_type,
  m.content,
  m.author,
  mt.target_role,
  mt.target_table,
  mt.target_id
FROM AGENTS.DBT_MODEL model
JOIN AGENTS.MEMORY_TARGET mt
  ON mt.target_table = 'AGENTS.DBT_MODEL'
 AND mt.target_id = AGENTS.RESOLVE_ID('AGENTS.DBT_MODEL', model.unique_id)
JOIN AGENTS.MEMORY m ON m.memory_id = mt.memory_id
WHERE model.unique_id = 'model.analytics.fct_revenue'
ORDER BY m.created_at DESC;
```

The first query does not need to know whether a memory points at a dbt model, a dbt column, a lineage edge, a Fivetran connector, or several of them at once. It only needs the common `AGENTS.ENTITY` projection. Follow-up queries that need provider-specific columns still need to join to the specific provider table or use generated SQL.

---

## Provider-Contributed Tables

Providers may contribute additional tables to the `AGENTS` schema. To prevent name conflicts, all such tables must follow this naming convention:

```
AGENTS.{PROVIDER}_{TABLE_NAME}
```

The `PROVIDER` prefix must exactly match the `provider` value used in `AGENTS.ROOT`. Providers should document each contributed table in `AGENTS.ROOT` with an appropriate `key`.

**Example:** If `provider = 'acme_corp'`, contributed tables must be named `AGENTS.ACME_CORP_*`.

Every provider-contributed table must declare a primary key. This applies even when the underlying warehouse treats primary keys as informational rather than enforced constraints. The declaration is still part of the metadata contract and is used by consumers, generated views, and optional resolver helpers.

If a provider-contributed table contains rows meant to be referenced through polymorphic attachments, it should be included in `AGENTS.ENTITY`. This can apply to object tables, relationship tables, logs, or event streams. Tables only need an `AGENTS.ENTITY` branch when their individual rows should be addressable through the common projection.

---

## Well-Known Extensions

Well-known extensions are provider-contributed tables from specific vendors that tools may query directly — without reading `AGENTS.ROOT` first — because their schema is part of this specification. Providers should still register them in `AGENTS.ROOT`, but the schemas here are stable and publicly documented.

This means there are two valid discovery paths:
- generic discovery: start at `AGENTS.ROOT`, read provider descriptions, then inspect the referenced tables
- shortcut discovery: if a tool already knows a well-known extension, it may query those tables directly

The first path is the default and is what makes the Agents Schema self-describing. The second path exists for convenience and interoperability with tools that want to consume a stable schema without first reading provider-written descriptions.

---

## Extension: `fivetran`

The Fivetran extension surfaces metadata from the [Fivetran Platform Connector](https://fivetran.com/docs/logs/fivetran-platform): the connectors ingesting data, the destinations they write to, the structural schema of synced data, and recent sync health.

Agents can use this extension to understand where raw data came from, when it was last updated, and whether any connectors are in a degraded state.

### `AGENTS.FIVETRAN_CONNECTOR`

One row per Fivetran connector (called a "connection" in the Fivetran UI).

```sql
CREATE TABLE AGENTS.FIVETRAN_CONNECTOR (
  connector_id     VARCHAR NOT NULL PRIMARY KEY,
  connector_name   VARCHAR NOT NULL,
  connector_type   VARCHAR NOT NULL,  -- e.g. 'postgres', 'salesforce', 'stripe'
  destination_id   VARCHAR NOT NULL,
  destination_name VARCHAR NOT NULL,
  destination_schema VARCHAR NOT NULL, -- the schema written to in the warehouse
  status           VARCHAR NOT NULL,  -- 'ACTIVE', 'BROKEN', 'PAUSED', 'DELETED'
  sync_frequency   INTEGER,           -- minutes between syncs, NULL if unscheduled
  last_synced_at   TIMESTAMP,
  created_at       TIMESTAMP NOT NULL,
  description      TEXT               -- optional human-written notes
);
```

| Column | Description |
|---|---|
| `connector_id` | Stable Fivetran-assigned identifier. |
| `connector_type` | The source application type. Use this to understand the origin system. |
| `destination_schema` | The schema in the warehouse where this connector writes its tables. Join to `AGENTS.FIVETRAN_TABLE.schema_name` to enumerate tables. |
| `status` | `BROKEN` or `PAUSED` connectors may mean stale data downstream. |
| `last_synced_at` | When the most recent successful sync completed. |

### `AGENTS.FIVETRAN_TABLE`

One row per synced table, across all connectors.

```sql
CREATE TABLE AGENTS.FIVETRAN_TABLE (
  connector_id  VARCHAR NOT NULL,
  schema_name   VARCHAR NOT NULL,  -- warehouse schema (matches destination_schema)
  table_name    VARCHAR NOT NULL,
  enabled       BOOLEAN NOT NULL,  -- whether this table is included in syncs
  row_count     BIGINT,            -- approximate, as of last sync
  last_synced_at TIMESTAMP,
  PRIMARY KEY (connector_id, schema_name, table_name)
);
```

### `AGENTS.FIVETRAN_COLUMN`

One row per synced column.

```sql
CREATE TABLE AGENTS.FIVETRAN_COLUMN (
  connector_id    VARCHAR NOT NULL,
  schema_name     VARCHAR NOT NULL,
  table_name      VARCHAR NOT NULL,
  column_name     VARCHAR NOT NULL,
  data_type       VARCHAR,
  is_primary_key  BOOLEAN NOT NULL DEFAULT FALSE,
  enabled         BOOLEAN NOT NULL,
  PRIMARY KEY (connector_id, schema_name, table_name, column_name)
);
```

### `AGENTS.FIVETRAN_SYNC_LOG`

Recent sync events — errors, warnings, and completions — for connector health monitoring. Agents should query this to understand whether data freshness issues are due to connector failures.

```sql
CREATE TABLE AGENTS.FIVETRAN_SYNC_LOG (
  log_id        VARCHAR NOT NULL PRIMARY KEY,
  connector_id  VARCHAR NOT NULL,
  sync_id       VARCHAR,
  occurred_at   TIMESTAMP NOT NULL,
  event_type    VARCHAR NOT NULL,    -- 'INFO', 'WARNING', 'ERROR', 'SEVERE'
  message       TEXT NOT NULL,
  message_data  VARIANT              -- structured JSON payload for ERROR/SEVERE events
);
```

| Column | Description |
|---|---|
| `event_type` | `WARNING` and `ERROR` entries indicate transient issues; `SEVERE` typically means the connector is broken and requires intervention. |
| `message_data` | JSON blob with structured context. For schema change events, contains `schema_name` and `table_name`. |

Suggested query for agents checking data freshness:

```sql
SELECT connector_name, status, last_synced_at,
       DATEDIFF('hour', last_synced_at, CURRENT_TIMESTAMP) AS hours_since_sync
FROM AGENTS.FIVETRAN_CONNECTOR
WHERE status != 'PAUSED'
ORDER BY hours_since_sync DESC NULLS FIRST;
```

---

## Extension: `dbt`

The dbt extension provides a normalized, queryable representation of the information in dbt's `manifest.json`. It captures the transformation layer: what models exist, how they are documented, how they depend on each other, and what tests are defined.

Agents can use this extension to understand what "curated" tables exist (as opposed to raw ingested data), trace column lineage, find model owners, and assess test coverage.

For teams using dbt's Semantic Layer, this extension can also be extended with metadata normalized from `semantic_manifest.json`. That artifact captures semantic models, entities, dimensions, measures, metrics, and saved queries defined on top of dbt models.

### `AGENTS.DBT_MODEL`

One row per dbt model. Corresponds to `nodes` entries in `manifest.json` where `resource_type = 'model'`.

```sql
CREATE TABLE AGENTS.DBT_MODEL (
  unique_id        VARCHAR NOT NULL PRIMARY KEY, -- 'model.<package>.<name>'
  name             VARCHAR NOT NULL,
  package_name     VARCHAR NOT NULL,
  database_name    VARCHAR NOT NULL,  -- warehouse database
  schema_name      VARCHAR NOT NULL,  -- warehouse schema
  materialization  VARCHAR NOT NULL,  -- 'table', 'view', 'incremental', 'ephemeral'
  description      TEXT,              -- from schema.yml
  owner            VARCHAR,           -- from meta.owner or config.meta.owner
  tags             ARRAY,             -- list of string tags
  file_path        VARCHAR NOT NULL,  -- relative path to .sql file
  access           VARCHAR,           -- 'public', 'protected', 'private' (dbt 1.7+)
  contract_enforced BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP          -- manifest generation time
);
```

| Column | Description |
|---|---|
| `unique_id` | Globally unique. Use this to join to other dbt extension tables. |
| `materialization` | Ephemeral models have no warehouse object; agents should note this when suggesting queries. |
| `description` | Free-text documentation from `schema.yml`. Often the richest signal about what a model represents. |
| `owner` | Populated from `meta.owner` in `schema.yml`. Useful for routing questions about a model. |
| `access` | dbt's access modifier — `public` models are intended for broad use; `private` models are internal to their package. |

### `AGENTS.DBT_COLUMN`

One row per documented column on a model. Normalized from the `columns` map on each node in `manifest.json`.

```sql
CREATE TABLE AGENTS.DBT_COLUMN (
  model_unique_id  VARCHAR NOT NULL,  -- FK to AGENTS.DBT_MODEL.unique_id
  column_name      VARCHAR NOT NULL,
  data_type        VARCHAR,           -- declared type, may differ from warehouse DDL
  description      TEXT,
  tags             ARRAY,
  meta             VARIANT,           -- arbitrary key-value pairs from schema.yml
  PRIMARY KEY (model_unique_id, column_name)
);
```

### `AGENTS.DBT_SOURCE`

One row per dbt source table. Corresponds to `sources` entries in `manifest.json`.

```sql
CREATE TABLE AGENTS.DBT_SOURCE (
  unique_id      VARCHAR NOT NULL PRIMARY KEY, -- 'source.<package>.<source>.<table>'
  source_name    VARCHAR NOT NULL,             -- the source block name in schema.yml
  table_name     VARCHAR NOT NULL,             -- the individual table within the source
  database_name  VARCHAR NOT NULL,
  schema_name    VARCHAR NOT NULL,
  description    TEXT,
  loader         VARCHAR,                      -- e.g. 'fivetran', 'airbyte', 'stitch'
  freshness_warn_after_hours  INTEGER,
  freshness_error_after_hours INTEGER
);
```

| Column | Description |
|---|---|
| `loader` | Declared in `schema.yml`. When `loader = 'fivetran'`, join to `AGENTS.FIVETRAN_CONNECTOR` on `schema_name` to get sync health. |
| `freshness_*` | Thresholds from dbt source freshness configuration. |

### `AGENTS.DBT_DEPENDENCY`

The lineage graph: one row per directed edge in the DAG. Normalized from `parent_map` and `child_map` in `manifest.json`.

```sql
CREATE TABLE AGENTS.DBT_DEPENDENCY (
  upstream_id    VARCHAR NOT NULL,  -- unique_id of the upstream node
  downstream_id  VARCHAR NOT NULL,  -- unique_id of the downstream node
  upstream_type  VARCHAR NOT NULL,  -- 'model', 'source', 'seed', 'snapshot'
  downstream_type VARCHAR NOT NULL,
  PRIMARY KEY (upstream_id, downstream_id)
);
```

To find all models that depend (directly or indirectly) on a source, agents can walk this table recursively using a CTE. Example:

```sql
WITH RECURSIVE lineage AS (
  SELECT downstream_id AS node_id FROM AGENTS.DBT_DEPENDENCY
  WHERE upstream_id = 'source.my_project.fivetran_salesforce.account'
  UNION ALL
  SELECT d.downstream_id FROM AGENTS.DBT_DEPENDENCY d
  JOIN lineage l ON d.upstream_id = l.node_id
)
SELECT DISTINCT m.name, m.schema_name, m.description
FROM lineage JOIN AGENTS.DBT_MODEL m ON m.unique_id = lineage.node_id;
```

### `AGENTS.DBT_TEST`

One row per dbt test. Corresponds to `nodes` where `resource_type = 'test'`.

```sql
CREATE TABLE AGENTS.DBT_TEST (
  unique_id        VARCHAR NOT NULL PRIMARY KEY,
  test_name        VARCHAR NOT NULL,   -- e.g. 'not_null', 'unique', 'accepted_values'
  attached_to_id   VARCHAR NOT NULL,   -- unique_id of model or source being tested
  column_name      VARCHAR,            -- NULL for model-level tests
  severity         VARCHAR NOT NULL,   -- 'warn' or 'error'
  test_type        VARCHAR NOT NULL    -- 'generic' or 'singular'
);
```

### `AGENTS.DBT_EXPOSURE`

One row per dbt exposure: downstream consumers of dbt models such as dashboards, ML models, or applications.

```sql
CREATE TABLE AGENTS.DBT_EXPOSURE (
  unique_id    VARCHAR NOT NULL PRIMARY KEY,
  name         VARCHAR NOT NULL,
  type         VARCHAR NOT NULL,   -- 'dashboard', 'ml', 'application', 'analysis', 'notebook'
  description  TEXT,
  owner_name   VARCHAR,
  owner_email  VARCHAR,
  url          VARCHAR,
  tags         ARRAY
);
```

```sql
-- Which exposures depend on a given model?
SELECT e.name, e.type, e.owner_email, e.url
FROM AGENTS.DBT_EXPOSURE e
JOIN AGENTS.DBT_DEPENDENCY d ON d.downstream_id = e.unique_id
WHERE d.upstream_id = 'model.my_project.fct_orders';
```

### Semantic Layer Sketch

dbt's Semantic Layer sits one level above the core DAG metadata above. A practical representation in the Agents Schema is:
- keep `AGENTS.DBT_MODEL` as the physical/modeling layer
- add semantic-layer tables sourced from `semantic_manifest.json`
- link each semantic model back to exactly one dbt model
- normalize reusable semantic primitives separately from queryable metrics

That yields a shape like this:

### `AGENTS.DBT_SEMANTIC_MODEL`

One row per semantic model. Corresponds to semantic model definitions in `semantic_manifest.json`.

```sql
CREATE TABLE AGENTS.DBT_SEMANTIC_MODEL (
  unique_id             VARCHAR NOT NULL PRIMARY KEY, -- 'semantic_model.<package>.<name>'
  name                  VARCHAR NOT NULL,
  package_name          VARCHAR NOT NULL,
  model_unique_id       VARCHAR NOT NULL,            -- FK to AGENTS.DBT_MODEL.unique_id
  node_relation_name    VARCHAR,                     -- rendered warehouse relation, if available
  description           TEXT,
  default_time_dimension VARCHAR,
  primary_entity_name   VARCHAR,
  label                 VARCHAR,
  config                VARIANT,                     -- semantic-model-specific config
  created_at            TIMESTAMP
);
```

This is the anchor table for the semantic graph. If an agent needs to answer "what business object is this metric defined on?", it should start here and then traverse dimensions, entities, and measures.

### `AGENTS.DBT_SEMANTIC_ENTITY`

One row per entity on a semantic model. Entities are the join keys that connect semantic models.

```sql
CREATE TABLE AGENTS.DBT_SEMANTIC_ENTITY (
  semantic_model_unique_id VARCHAR NOT NULL,
  entity_name              VARCHAR NOT NULL,
  entity_type              VARCHAR NOT NULL, -- 'primary', 'unique', 'foreign', 'natural'
  expr                     VARCHAR,          -- source expression if name differs from column
  role                     VARCHAR,          -- optional semantic role if dbt surfaces one
  description              TEXT,
  PRIMARY KEY (semantic_model_unique_id, entity_name)
);
```

This table is the semantic analogue of `AGENTS.DBT_DEPENDENCY`: instead of DAG edges, it describes the join surface MetricFlow can use at query time.

### `AGENTS.DBT_SEMANTIC_DIMENSION`

One row per dimension exposed by a semantic model.

```sql
CREATE TABLE AGENTS.DBT_SEMANTIC_DIMENSION (
  semantic_model_unique_id VARCHAR NOT NULL,
  dimension_name           VARCHAR NOT NULL,
  dimension_type           VARCHAR NOT NULL, -- 'categorical', 'time'
  expr                     VARCHAR,
  data_type                VARCHAR,
  description              TEXT,
  label                    VARCHAR,
  type_params              VARIANT,          -- time granularity / validity params / etc.
  is_partition             BOOLEAN,
  PRIMARY KEY (semantic_model_unique_id, dimension_name)
);
```

Time dimensions belong here, including the semantic model's default aggregation time dimension.

### `AGENTS.DBT_SEMANTIC_MEASURE`

One row per measure on a semantic model. Measures are the raw aggregations from which many metrics are built.

```sql
CREATE TABLE AGENTS.DBT_SEMANTIC_MEASURE (
  semantic_model_unique_id   VARCHAR NOT NULL,
  measure_name               VARCHAR NOT NULL,
  agg                        VARCHAR NOT NULL, -- 'sum', 'count', 'count_distinct', 'avg', ...
  expr                       VARCHAR,
  data_type                  VARCHAR,
  description                TEXT,
  label                      VARCHAR,
  agg_time_dimension         VARCHAR,
  non_additive_dimension_name VARCHAR,
  create_metric              BOOLEAN,
  config                     VARIANT,
  PRIMARY KEY (semantic_model_unique_id, measure_name)
);
```

This lets agents distinguish between:
- base semantic measures, which are directly aggregatable
- user-facing metrics, which may wrap one or more measures with additional logic

### `AGENTS.DBT_METRIC`

One row per metric exposed by the Semantic Layer.

```sql
CREATE TABLE AGENTS.DBT_METRIC (
  unique_id       VARCHAR NOT NULL PRIMARY KEY, -- 'metric.<package>.<name>'
  name            VARCHAR NOT NULL,
  package_name    VARCHAR NOT NULL,
  metric_type     VARCHAR NOT NULL,             -- e.g. 'simple', 'ratio', 'derived', 'cumulative'
  label           VARCHAR,
  description     TEXT,
  type_params     VARIANT,                      -- metric-type-specific configuration
  filter_sql      TEXT,
  time_grains     ARRAY,                        -- supported grains if materialized in artifact
  dimensions      ARRAY,                        -- allowed dimensions if materialized in artifact
  created_at      TIMESTAMP
);
```

`type_params` is important here because dbt metric definitions vary by type. For example:
- a simple metric points at a measure
- a ratio metric has numerator/denominator inputs
- a derived metric references other metrics
- a cumulative metric carries windowing semantics

### `AGENTS.DBT_METRIC_INPUT`

One row per metric input, so agents can trace how a metric is assembled.

```sql
CREATE TABLE AGENTS.DBT_METRIC_INPUT (
  metric_unique_id         VARCHAR NOT NULL,
  input_order              INTEGER NOT NULL,
  input_kind               VARCHAR NOT NULL, -- 'measure', 'metric'
  semantic_model_unique_id VARCHAR,          -- set when input_kind = 'measure'
  measure_name             VARCHAR,          -- set when input_kind = 'measure'
  input_metric_unique_id   VARCHAR,          -- set when input_kind = 'metric'
  role                     VARCHAR,          -- 'numerator', 'denominator', 'operand', etc.
  params                   VARIANT,          -- alias/window/offset/filter per input
  PRIMARY KEY (metric_unique_id, input_order)
);
```

Without this table, an agent can list metrics but cannot explain them. With it, an agent can answer questions like "what does gross_margin depend on?" or "is revenue a direct sum or a derived metric?"

### `AGENTS.DBT_SAVED_QUERY`

One row per saved query. Saved queries package a set of metrics plus dimensions, filters, and grain into a reusable query definition.

```sql
CREATE TABLE AGENTS.DBT_SAVED_QUERY (
  unique_id        VARCHAR NOT NULL PRIMARY KEY, -- 'saved_query.<package>.<name>'
  name             VARCHAR NOT NULL,
  package_name     VARCHAR NOT NULL,
  description      TEXT,
  label            VARCHAR,
  query_params     VARIANT,                      -- exported grain, filters, limits, etc.
  created_at       TIMESTAMP
);
```

### `AGENTS.DBT_SAVED_QUERY_ITEM`

One row per metric or dimension selected by a saved query.

```sql
CREATE TABLE AGENTS.DBT_SAVED_QUERY_ITEM (
  saved_query_unique_id   VARCHAR NOT NULL,
  item_order              INTEGER NOT NULL,
  item_kind               VARCHAR NOT NULL, -- 'metric', 'dimension'
  metric_unique_id        VARCHAR,
  semantic_model_unique_id VARCHAR,
  dimension_name          VARCHAR,
  params                  VARIANT,
  PRIMARY KEY (saved_query_unique_id, item_order)
);
```

This keeps saved queries queryable without baking every semantic-layer concept into one opaque JSON blob.

### Why represent it this way?

This shape preserves the same design choices used elsewhere in the Agents Schema:
- one table per stable concept
- relational joins for the most common agent questions
- `VARIANT` only where dbt's schema is genuinely polymorphic

It also lets agents answer distinct classes of questions cleanly:
- physical layer: "what warehouse relation does this come from?" via `AGENTS.DBT_MODEL`
- semantic graph: "what can join to what?" via `AGENTS.DBT_SEMANTIC_ENTITY`
- query surface: "what dimensions/measures exist?" via `AGENTS.DBT_SEMANTIC_DIMENSION` and `AGENTS.DBT_SEMANTIC_MEASURE`
- governed business logic: "what is the canonical metric?" via `AGENTS.DBT_METRIC` and `AGENTS.DBT_METRIC_INPUT`
- reusable consumption patterns: "what metric bundles are already curated?" via `AGENTS.DBT_SAVED_QUERY*`

Example: trace a metric back to its underlying dbt model(s):

```sql
SELECT
  m.name AS metric_name,
  sm.name AS semantic_model_name,
  dm.schema_name,
  dm.name AS dbt_model_name,
  mi.role,
  mi.measure_name
FROM AGENTS.DBT_METRIC m
JOIN AGENTS.DBT_METRIC_INPUT mi
  ON mi.metric_unique_id = m.unique_id
JOIN AGENTS.DBT_SEMANTIC_MODEL sm
  ON sm.unique_id = mi.semantic_model_unique_id
JOIN AGENTS.DBT_MODEL dm
  ON dm.unique_id = sm.model_unique_id
WHERE m.unique_id = 'metric.analytics.revenue';
```

If you wanted to keep the first version smaller, the minimum viable addition would be just:
- `AGENTS.DBT_SEMANTIC_MODEL`
- `AGENTS.DBT_SEMANTIC_ENTITY`
- `AGENTS.DBT_SEMANTIC_DIMENSION`
- `AGENTS.DBT_SEMANTIC_MEASURE`
- `AGENTS.DBT_METRIC`
- `AGENTS.DBT_METRIC_INPUT`

That covers the core semantic graph and metric definitions; saved queries can be added later.

---

## Cross-Extension Queries

One of the most valuable things agents can do is join across extensions. Example: finding raw source tables that feed a specific dbt model, then checking whether those sources' Fivetran connectors are healthy.

```sql
-- Trace a dbt model back to its Fivetran connectors and check sync health
WITH RECURSIVE upstream AS (
  SELECT upstream_id AS node_id, upstream_type
  FROM AGENTS.DBT_DEPENDENCY
  WHERE downstream_id = 'model.analytics.fct_revenue'
  UNION ALL
  SELECT d.upstream_id, d.upstream_type
  FROM AGENTS.DBT_DEPENDENCY d
  JOIN upstream u ON d.downstream_id = u.node_id
)
SELECT
  s.source_name,
  s.schema_name,
  c.connector_name,
  c.connector_type,
  c.status,
  c.last_synced_at
FROM upstream u
JOIN AGENTS.DBT_SOURCE s      ON s.unique_id = u.node_id
JOIN AGENTS.FIVETRAN_CONNECTOR c ON c.destination_schema = s.schema_name
WHERE u.upstream_type = 'source';
```

---

## Conventions and Guidance for Implementors

### Populating the tables

Agents Schema tables are typically populated by:
- **Vendor-run pipelines** (e.g. the Fivetran Platform Connector syncing to `AGENTS.FIVETRAN_*`)
- **CI/CD jobs** (e.g. a dbt post-deploy step that parses `manifest.json` and loads `AGENTS.DBT_*`)
- **Platform engineering teams** maintaining custom provider tables

### Staleness

Providers should expose freshness using provider-native fields where they have them, such as `last_synced_at`, or through a documented companion `AGENTS.{PROVIDER}_SYNC_STATUS` table. Agents should check freshness before drawing conclusions about current state.

Providers may also expose catalog-row lifecycle and provenance fields when they can produce them accurately:
- `_created_at`: when this catalog row first appeared
- `_updated_at`: when this catalog row was last updated by the provider
- `_deleted_at`: soft-delete timestamp; consumers should filter `_deleted_at IS NULL` when this column is present and they want current rows
- `_contribution_id`: identifier for the sync, batch, deploy, or agent contribution that wrote the row

These fields are operational metadata about the catalog row, not the source object. They are optional; providers should not invent them if they cannot maintain them correctly.

Implementations that expose `AGENTS.ENTITY` may also project any available lifecycle fields there, such as `created_at`, `updated_at`, `deleted_at`, or `contribution_id`, when they want generic freshness or provenance checks across heterogeneous provider rows.

### Permissions

- `AGENTS.ROOT` and all extension tables should be readable by any warehouse principal that runs analytical queries.
- Write access should be tightly controlled — only the owning system should insert or update rows.

### Reserved providers

The following provider names are reserved by this specification:

| Provider | Reserved for |
|---|---|
| `fivetran` | Fivetran Platform Connector extension (this spec) |
| `dbt` | dbt manifest extension (this spec) |
| `agents_schema` | Future use by the Agents Schema specification itself |

---

## Summary of All Tables

| Table | Provider | Purpose |
|---|---|---|
| `AGENTS.ROOT` | *(core)* | Registry of all metadata providers and sections |
| `AGENTS.FIVETRAN_CONNECTOR` | fivetran | One row per Fivetran connector |
| `AGENTS.FIVETRAN_TABLE` | fivetran | Synced tables with row counts and freshness |
| `AGENTS.FIVETRAN_COLUMN` | fivetran | Column-level schema for synced tables |
| `AGENTS.FIVETRAN_SYNC_LOG` | fivetran | Recent sync events, errors, and warnings |
| `AGENTS.DBT_MODEL` | dbt | dbt models with documentation, owner, materialization |
| `AGENTS.DBT_COLUMN` | dbt | Per-column documentation for dbt models |
| `AGENTS.DBT_SOURCE` | dbt | dbt source declarations with freshness thresholds |
| `AGENTS.DBT_DEPENDENCY` | dbt | DAG edges for upstream/downstream lineage |
| `AGENTS.DBT_TEST` | dbt | Test definitions and which columns they cover |
| `AGENTS.DBT_EXPOSURE` | dbt | Downstream consumers (dashboards, apps, ML models) |
| `AGENTS.DBT_SEMANTIC_MODEL` | dbt | Semantic models defined on top of dbt models |
| `AGENTS.DBT_SEMANTIC_ENTITY` | dbt | Joinable entities/keys for semantic models |
| `AGENTS.DBT_SEMANTIC_DIMENSION` | dbt | Queryable semantic dimensions |
| `AGENTS.DBT_SEMANTIC_MEASURE` | dbt | Base semantic measures and aggregation rules |
| `AGENTS.DBT_METRIC` | dbt | User-facing governed metrics |
| `AGENTS.DBT_METRIC_INPUT` | dbt | Metric composition and dependencies |
| `AGENTS.DBT_SAVED_QUERY` | dbt | Reusable saved metric queries |
| `AGENTS.DBT_SAVED_QUERY_ITEM` | dbt | Metrics/dimensions selected by saved queries |
