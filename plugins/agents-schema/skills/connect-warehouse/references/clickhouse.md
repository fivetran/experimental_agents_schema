# ClickHouse

Use the clickhouse-connect driver over the HTTP interface.

1. Read the required `host` and optional `port`, `user`, `password`, and `secure` values from
   `agents.yml`. Ask the user to add `host` if it is missing without pasting secrets into chat.
   `port` defaults to 8443 when `secure` is true and 8123 otherwise; `user` defaults to
   `default`, and `password` defaults to an empty string for passwordless deployments.
2. Install `clickhouse-connect` when `clickhouse_connect` is unavailable.
3. Verify the connection by replacing `<SQL>` with `SELECT 1`:

   ```bash
   python3 - <<'PYEOF'
   import json
   import clickhouse_connect
   import yaml

   with open("agents.yml") as config_file:
       cfg = yaml.safe_load(config_file)
   secure = cfg.get("secure", True)
   if isinstance(secure, str):
       values = {"true": True, "1": True, "yes": True,
                 "false": False, "0": False, "no": False}
       try:
           secure = values[secure.strip().lower()]
       except KeyError as exc:
           raise ValueError("agents.yml secure must be true or false") from exc
   if not isinstance(secure, bool):
       raise ValueError("agents.yml secure must be true or false")
   client = clickhouse_connect.get_client(
       host=cfg["host"],
       port=cfg.get("port"),
       username=cfg.get("user", "default"),
       password=cfg.get("password", ""),
       secure=secure,
   )
   try:
       result = client.query("""
   <SQL>
       """)
       rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
       print(json.dumps(rows, indent=2, default=str))
   finally:
       client.close()
   PYEOF
   ```

Note: ClickHouse identifiers are case-sensitive and the metadata lives in the
lowercase `agents` database (`agents.root`, not `AGENTS.ROOT`).
