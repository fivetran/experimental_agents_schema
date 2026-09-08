# Sigma Setup

## Prerequisites

Configure the `WAREHOUSE_CREDENTIALS` GitHub Actions secret for your destination
warehouse. Copy the YAML for your destination, fill in your values, and save it
as the `WAREHOUSE_CREDENTIALS` GitHub Actions secret in the repository that
calls this workflow.

<details>
<summary>Snowflake setup</summary>

We recommend key-pair authentication:

```yaml
type: snowflake
account: abc123
user: AGENTS_SCHEMA_BOT
warehouse: COMPUTE_WH
database: ANALYTICS
role: TRANSFORMER
private_key_pem: |
  -----BEGIN ENCRYPTED PRIVATE KEY-----
  MIIEvQIBADANBgkqh...
  -----END ENCRYPTED PRIVATE KEY-----
private_key_passphrase: your-passphrase   # only if the key is encrypted
```

`role` is optional. An unencrypted key uses `-----BEGIN PRIVATE KEY-----` /
`-----END PRIVATE KEY-----` markers and omits `private_key_passphrase`.

Password auth is also supported by replacing the private key fields with:

```yaml
password: your-password
```

</details>

<details>
<summary>Databricks setup</summary>

Use a SQL warehouse HTTP path and a personal access token:

```yaml
type: databricks
host: dbc-abc123.cloud.databricks.com
http_path: /sql/1.0/warehouses/abc123
catalog: main
token: your-personal-access-token
```

The token needs permission to create and write tables in the `agents` schema
within the configured catalog.

</details>

<details>
<summary>BigQuery setup</summary>

Use the destination project plus a service account JSON object:

```yaml
type: bigquery
project_id: my-gcp-project
location: US
credentials_json:
  type: service_account
  project_id: service-account-project
  private_key_id: ...
  private_key: |
    -----BEGIN PRIVATE KEY-----
    ...
    -----END PRIVATE KEY-----
  client_email: agents-schema@my-gcp-project.iam.gserviceaccount.com
  client_id: ...
  auth_uri: https://accounts.google.com/o/oauth2/auth
  token_uri: https://oauth2.googleapis.com/token
  auth_provider_x509_cert_url: https://www.googleapis.com/oauth2/v1/certs
  client_x509_cert_url: ...
```

`location` is optional. The service account needs permission to create datasets
and create, load, query, update, and delete tables in the destination project.

</details>

<details>
<summary>ClickHouse setup</summary>

Use the HTTP interface host plus a user with rights on the `agents` database:

```yaml
type: clickhouse
host: abc123.region.clickhouse.cloud
port: 8443
user: agents_schema_bot
password: your-password
secure: true
```

See [clickhouse-setup.md](clickhouse-setup.md) for grants, type mapping, and
replicated-cluster notes.

</details>

## Obtain Sigma Data Model YAML Files

Sigma data model YAML files are obtained from the Sigma REST API using the
[Get the code representation of a data model](https://help.sigmacomputing.com/reference/getdatamodelspec)
endpoint.

Export each data model you want to publish with:

```bash
curl -s \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/yaml" \
  "https://api.sigmacomputing.com/v2/dataModels/{dataModelId}/spec?format=yaml" \
  > sigma/my_data_model.sigma.yaml
```

Save each exported file with the `.sigma.yaml` extension in a directory in your
repository. The example below uses `sigma`:

```text
sigma/
  orders.sigma.yaml
  pipeline.sigma.yaml
```

## Run the Sigma Sync Workflow

Use the Sigma workflow when your repository contains exported Sigma data model
YAML files:

```yaml
name: Agents Schema Sigma

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-sigma:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-sigma.yml@v0.0.11
    with:
      sigma-dir: sigma
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
```

`sigma-dir` is required — set it to the directory that contains your
`*.sigma.yaml` files. The example uses `sigma`; change it to match your
repository.

The workflow writes:

- `AGENTS.SIGMA_DATA_MODEL`
- `AGENTS.SIGMA_ELEMENT`
- `AGENTS.SIGMA_COLUMN`
- `AGENTS.SIGMA_METRIC`

These jobs do not need to depend on dbt or Looker jobs unless your repository
has its own ordering requirement.

## Metric coverage

Only metrics that use a single standard aggregation over one column are written
to `AGENTS.SIGMA_METRIC`:

```
Sum([table/column])   Avg([table/column])   Count([table/column])
CountDistinct([table/column])   Min([table/column])   Max([table/column])
```

The following are **not** written because they do not map cleanly to a single
SQL aggregate expression:

- Conditional aggregations — `SumIf(...)`, `CountIf(...)`, `CountDistinctIf(...)`
- Cross-metric references — `[Metrics/Revenue] / [Metrics/Total COGS]`
- Multi-field expressions — `Sum([Quantity] * [Price])`
- Statistical functions — `PercentileCont([Amount], 0.9)`
- No-argument calls — `Count()`

These metrics are silently skipped. Agents querying `AGENTS.SIGMA_METRIC` will
only see metrics that have a direct SQL aggregate equivalent.
