# ClickHouse Setup

## Credentials

Set the `WAREHOUSE_CREDENTIALS` GitHub Actions secret (or environment variable
for local runs) to:

```yaml
type: clickhouse
host: abc123.region.clickhouse.cloud   # or your self-hosted host
port: 8443                             # optional; defaults to the driver default (8443 secure / 8123 plain)
user: agents_schema_bot                # optional; defaults to "default"
password: your-password
secure: true                           # optional; defaults to true — set false for plain HTTP
```

The connection uses the ClickHouse HTTP interface via
[clickhouse-connect](https://github.com/ClickHouse/clickhouse-connect). The
least-privilege setup is for an admin to create the `agents` database once and
grant the sync user rights only inside it:

```sql
CREATE DATABASE IF NOT EXISTS agents;
GRANT CREATE TABLE, DROP TABLE, TRUNCATE, SELECT, INSERT, ALTER DELETE, ALTER UPDATE ON agents.* TO agents_schema_bot;
-- Only if the server sets table_engines_require_grant = true (off by default):
GRANT TABLE ENGINE ON MergeTree TO agents_schema_bot;
```

(`ALTER UPDATE` is required alongside `ALTER DELETE` because lightweight
deletes are executed as an update of the internal `_row_exists` column.)

(`TABLE ENGINE` privileges are only enforced when `config.xml` sets
`<access_control_improvements><table_engines_require_grant>true</...>`. The
default is `false`, and ClickHouse Cloud does not enable it, so most
deployments can skip that line; granting it anyway is harmless.)

(The writer checks `system.databases` first and only issues
`CREATE DATABASE IF NOT EXISTS agents` when the database is missing — in
ClickHouse, `IF NOT EXISTS` still requires the `CREATE DATABASE` grant even
when the database already exists. Grant `CREATE DATABASE ON agents.*` to the
sync user only if you want it to bootstrap the database itself.)

Grant read access broadly so agents can consume the metadata:

```sql
GRANT SELECT ON agents.* TO your_analyst_role;
```

## How the AGENTS schema maps to ClickHouse

ClickHouse has a two-level `database.table` namespace, so the `AGENTS` schema
is a ClickHouse **database** named `agents`. ClickHouse identifiers are
case-sensitive and the writer creates the package's canonical lowercase names:
query `agents.root`, not `AGENTS.ROOT`.

Destination-specific mapping:

| Spec concept | ClickHouse |
|---|---|
| `AGENTS` schema | `agents` database |
| `varchar` / `text` columns | `String` (`Nullable(String)` when nullable) |
| `boolean` columns | `Bool` |
| `array` columns | `Array(String)`; non-string elements are stored as JSON text. A non-list value (OSI `ai_context` can be a plain string or an object) becomes a single element |
| `json` columns | native `JSON` on 25.3+, `String` holding JSON text on older servers |
| `PRIMARY KEY` | MergeTree `ORDER BY` key (ClickHouse does not enforce uniqueness) |
| Table replacement | `CREATE OR REPLACE TABLE` (statement-atomic) + `INSERT` |
| `ROOT` upserts | scoped lightweight `DELETE` of incoming keys + `INSERT` |

Because ClickHouse does not enforce primary keys, row uniqueness is maintained
by the publish path (full table replacement per source family; delete-then-insert
for `agents.root`), not by the engine. This assumes one sync process runs at a
time — the same assumption the sequential sync workflows make. Publishing is not
transactional: a concurrent reader can briefly observe an empty family table
during replacement, or a missing `root` row between the delete and the insert.
Rerunning the sync repairs an interrupted publish (every operation is
idempotent). Treat the tables as generated metadata, not hand-edited state.

## Deployment notes

- **ClickHouse Cloud:** works out of the box — Cloud internally rewrites
  `MergeTree` DDL to `SharedMergeTree`, so both metadata and data are shared by
  all nodes.
- **Self-hosted single node:** works on the default `Atomic` database engine
  when the ClickHouse data filesystem supports atomic exchange via
  `renameat2(RENAME_EXCHANGE)`, which `CREATE OR REPLACE TABLE` requires. Some
  network and FUSE filesystems, including NFS/EFS and CephFS, do not support
  this operation; use supported local storage or see
  [ClickHouse issue #96835](https://github.com/ClickHouse/ClickHouse/issues/96835).
- **Self-hosted replicated clusters:** the writer creates plain `MergeTree`
  tables, so table **data lives only on the node the sync connects to** (a
  `Replicated` database engine would replicate DDL, not MergeTree data). Point
  the sync and all metadata readers at the same node, or front it with a
  load-balancer rule. Native `ReplicatedMergeTree` support is a possible
  follow-up if there is demand.
- **Minimum version:** 24.8+ recommended (recursive CTEs for the lineage
  queries in [SPEC.md](SPEC.md)); the native `JSON` column type is used on
  25.3+ and falls back to `String` on older servers.

## Local smoke test

```bash
docker run -d --name ch -p 8123:8123 -e CLICKHOUSE_PASSWORD=dev clickhouse/clickhouse-server
export WAREHOUSE_CREDENTIALS='{"type":"clickhouse","host":"localhost","port":8123,"password":"dev","secure":false}'
agents-schema dbt --project-dir path/to/dbt/project
docker exec ch clickhouse-client --password dev --query "SELECT provider, key FROM agents.root"
```
