# dbt Setup

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
replicated-cluster notes. Managed dbt parse supports profiles with
`type: clickhouse` (the [dbt-clickhouse](https://github.com/ClickHouse/dbt-clickhouse)
adapter).

</details>

## Run the dbt Sync Workflow

In your dbt project repository, set up a new GitHub Workflow from the Actions tab. 

NOTE: Requires a dbt `manifest.json` file. If you don't have an existing manifest, produce it and check it into your dbt project's repository.

```yaml
name: Agents Schema dbt

on:
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  agents-schema-dbt:
    uses: dbt-labs/agents_schema/.github/workflows/agents-schema-dbt.yml@v0.0.11
    with:
      dbt-project-dir: dbt_project
    secrets:
      WAREHOUSE_CREDENTIALS: ${{ secrets.WAREHOUSE_CREDENTIALS }}
```

`dbt-project-dir` is required — set it to the path of your dbt project (the
directory that contains `dbt_project.yml`). The example uses `dbt_project`;
change it to match your repository.

The workflow looks for:

```text
<dbt project>/target/manifest.json
```
