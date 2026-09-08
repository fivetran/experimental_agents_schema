---
name: agents-schema-analyst-clickhouse
description: Use when answering a business data question (revenue, MRR, ARR, churn, customer or connector counts, etc.) against a ClickHouse database that has an agents metadata database. Triggers on questions like "what is our current MRR", "net revenue year-to-date", "how many active customers", or any ask for a governed metric instead of a guessed one.
allowed-tools: "Bash(clickhouse:*), Bash(curl:*), Read"
user-invocable: true
argument-hint: "[business question]"
---

# Agents Schema Analyst (ClickHouse)

## Overview

Answer the question by first reading the governed definitions in the database's `agents`
metadata database, then querying the business tables exactly as those definitions specify.

**Core principle: the database tells you how to compute the answer. Your job is to find
that instruction in `agents.*` and follow it — not to guess a formula, table, filter, or date rule.**

## Setup

- Query ClickHouse **read-only** with: `clickhouse client --query "<SQL>"` (add
  `--host/--secure/--password` as needed), or via HTTPS:
  `curl -sS 'https://<host>:8443/?query=<url-encoded SQL>' -u <user>:<password>`.
- **Connection:** read connection settings from an `agents.yml` in the working directory if
  present. Otherwise use the local default; if ambiguous, ask the user which connection to use.
- **Metadata database:** `agents`. ClickHouse has a two-level namespace, so `agents.root` is a
  table in the `agents` database. **Identifiers are case-sensitive** — the metadata objects are
  lowercase (`agents.root`, not `AGENTS.ROOT`).
- Only `SELECT`. Never `INSERT`, `ALTER`, `DELETE`, `CREATE`, or `DROP`.

## Procedure

1. **Discover what metadata exists — don't assume which providers are present.**
   ```sql
   SELECT provider, key, content FROM agents.root ORDER BY provider, key;
   ```
   This lists the providers that published metadata (`osi`, `lookml`, `dbt`, or user-published) plus
   their overview/guidance rows. Only query tables for providers that actually appear here.

2. **Find the metric.** Search the semantic definition tables for keywords from the question
   and read `description`, `ai_context`, and the formula (`expression` for OSI, `sql` for LookML).
   Substitute a keyword from the question for `<keyword>`:
   ```sql
   SELECT name, description, ai_context, expressions
   FROM agents.osi_metric
   WHERE lower(coalesce(name,'')||' '||coalesce(description,'')||' '||coalesce(toString(ai_context),''))
         LIKE '%<keyword>%';
   ```
   Use `agents.lookml_measure` (`sql`, `description`, `ai_context`) when the provider is LookML.
   Use `agents.omni_measure` (`sql`, `description`) when the provider is Omni.
   **If no rows match, stop and tell the user** — do not proceed to Step 3 without a metric
   definition. Try a shorter or alternate keyword if the first search returns nothing.
   OSI `expressions` holds a list of `{dialect, expression}` entries — prefer a `clickhouse`
   dialect entry when present, otherwise use the `ansi` or default entry.

3. **Resolve the physical table and its rules.** Find the source table and every query caveat
   in the dataset/view metadata, and obey each `ai_context` instruction exactly:
   - OSI: `agents.osi_dataset` (`source`, `ai_context`), `agents.osi_field`
   - LookML: `agents.lookml_view` (`sql_table_name`), `agents.lookml_dimension`
   - Omni: `agents.omni_view` (`schema`, `table_name`, `description`), `agents.omni_dimension`;
     use `agents.omni_topic_join` to understand which views are reachable within a topic.
   - dbt, *only if present in root*: `agents.dbt_model` / `agents.dbt_column` add model and
     column descriptions. For dbt models, `schema_name` is the ClickHouse **database** of the
     model, so the relation is `schema_name.name`.
   Use the source table named in the metadata — not a same-named table you assume exists elsewhere.

4. **Check the table engine before aggregating.** ClickHouse tables backed by
   `ReplacingMergeTree`, `CollapsingMergeTree`, or `VersionedCollapsingMergeTree` (common for
   CDC-replicated data) can contain multiple row versions until merges complete. Check with:
   ```sql
   SELECT engine FROM system.tables WHERE database = '<db>' AND name = '<table>';
   ```
   Engine names may carry `Replicated`/`Shared` prefixes (`SharedReplacingMergeTree` on Cloud)
   — judge by the suffix. For Replacing engines, add `FINAL` after the table name
   (`FROM db.table FINAL`) or pick the latest row per key explicitly (e.g. `argMax` by the
   version column). For Collapsing engines, use `FINAL` or aggregate through the `Sign` column
   (e.g. `sum(value * Sign)`); `argMax` alone is not the collapsing semantic. Plain `MergeTree`
   and views need no special handling.

5. **Translate the formula to SQL.** OSI `expression` is usually plain SQL (e.g. `SUM(amount)`)
   — use it as-is against the resolved table. For LookML `sql`: `${TABLE}.col` → `col`;
   `${other_field}` → look that field up and substitute recursively; `{% if %}…{% else %} X {% endif %}`
   → use the `{% else %}` branch. For Omni `sql`: the value is a quoted column reference
   (e.g. `'"AMOUNT"'`) — strip the outer quotes and use the inner identifier directly.
   Dialect notes: use `dateDiff('unit', a, b)`, `toStartOfMonth(...)` for date math; string
   concat is `||` or `concat()`. On ClickHouse 25.3+ the `meta` columns are native JSON with
   direct path access (`meta.owner`); on older servers they are `String` holding JSON text, so
   use `JSONExtractString(meta, 'owner')` (check with `SELECT toTypeName(meta) FROM ... LIMIT 1`
   if unsure). Array columns such as OSI `expressions` hold JSON text per element: read fields
   with `JSONExtractString(expressions[1], 'dialect')`. `ai_context` is usually a single-element
   array holding either plain text or one JSON object (structured OSI context — read fields with
   `JSONExtractString(ai_context[1], 'instructions')`).

6. **Pick the time grain from metadata.** Use the time dimension the metadata marks
   (`osi_field.is_time_dimension`, or a LookML `dimension_group`). For "current"/snapshot
   metrics, use the latest available period. For "year-to-date", try wall-clock current year
   first; **if it returns no rows because the data is historical, do NOT report $0** — anchor to
   the latest year present in the table and clearly label the date range you used.

7. **Run it and answer.** Run the grounded query, show the SQL you ran, and state
   the answer plainly (round currency to whole dollars with a `$`; percentages to one decimal).

## Hard rules — never hard-code

- Discover every metric formula, source table, filter, and date column from `agents.*`. Do not
  bake business facts into this skill, the prompt, or your reasoning.
- Follow `ai_context` / `description` exactly. If it says to use one column or table and not
  another, do exactly that.
- Do not run `SHOW TABLES` or broad schema crawls. The metadata rows tell you where
  to look — use focused `SELECT`s derived from the question.
- If a definition is missing or ambiguous, say so. Do not substitute a guess.

## Metadata table shapes (reference)

A given database has only the families its `root` table lists.
ClickHouse is case-sensitive and case-preserving — business table and column names appear
exactly as they were created; the `agents.*` metadata objects are lowercase.

| Table | Key columns |
|---|---|
| `agents.root` | `provider`, `key`, `content` |
| `agents.osi_metric` | `model_name`, `name`, `description`, `ai_context`, `expressions` |
| `agents.osi_dataset` | `model_name`, `name`, `source`, `primary_key`, `unique_keys`, `description`, `synonyms`, `ai_context` |
| `agents.osi_field` | `dataset_name`, `name`, `description`, `ai_context`, `is_time_dimension`, `expressions` |
| `agents.lookml_measure` | `view_name`, `measure_name`, `type`, `sql`, `description`, `ai_context` |
| `agents.lookml_view` | `name`, `sql_table_name`, `description`, `ai_context` |
| `agents.lookml_dimension` | `view_name`, `field_name`, `field_kind`, `type`, `sql`, `description`, `ai_context` |
| `agents.omni_measure` | `view_name`, `measure_name`, `aggregate_type`, `sql`, `description` |
| `agents.omni_view` | `view_name`, `schema`, `table_name`, `description` |
| `agents.omni_dimension` | `view_name`, `field_name`, `sql`, `description` |
| `agents.omni_topic` | `topic_name`, `base_view`, `label`, `group_label`, `description`, `ai_context` |
| `agents.omni_topic_join` | `topic_name`, `from_view`, `to_view` |
| `agents.dbt_model` | `unique_id`, `name`, `schema_name`, `description`, `meta` |
| `agents.dbt_column` | `model_id`, `column_name`, `data_type`, `description`, `meta` |

## Common mistakes

| Mistake | Do instead |
|---|---|
| Picking a plausible-looking column or table for a metric | Read the metric/dataset `ai_context` and use exactly the column, table, and filter it names. |
| Aggregating a `ReplacingMergeTree` table without `FINAL` | Check `system.tables.engine` first (match the suffix — Cloud reports `Shared*`); use `FINAL`/`argMax` for Replacing engines, `FINAL`/`Sign`-aware sums for Collapsing engines. |
| Reporting `$0` / no result for "year-to-date" | If current-year returns no rows, the data is historical — anchor to the latest year present and label it. |
| Querying `AGENTS.ROOT` in uppercase | ClickHouse identifiers are case-sensitive; the metadata objects are lowercase `agents.root`. |
| Querying a metric from the wrong table | The dataset/view metadata names the `source` and any "use X not Y" caveat. Follow it. |
| Assuming a provider's tables exist | Check `agents.root` first; some databases have only OSI, only LookML, or only dbt. |
| `SHOW TABLES` to explore | Use focused `SELECT`s against the known `agents.*` tables. |
