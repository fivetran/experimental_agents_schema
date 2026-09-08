import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
CLAUDE_MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "agents-schema"


class PluginMarketplaceTests(unittest.TestCase):
    def test_marketplace_installs_agents_schema_plugin(self):
        marketplace = json.loads(MARKETPLACE_PATH.read_text())

        self.assertEqual(marketplace["name"], "agents-schema")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "agents-schema")
        self.assertEqual(entry["source"], {"source": "local", "path": "./plugins/agents-schema"})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )

    def test_plugin_contains_schema_search_and_connection_skills(self):
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())
        skill_root = PLUGIN_ROOT / manifest["skills"]
        skill_names = {path.parent.name for path in skill_root.glob("*/SKILL.md")}

        self.assertEqual(skill_names, {"agents-schema-search", "connect-warehouse"})
        schema_skill = (skill_root / "agents-schema-search" / "SKILL.md").read_text()
        self.assertIn("SELECT * FROM agents.root ORDER BY provider, key;", schema_skill)
        self.assertNotIn("SELECT * FROM AGENTS.ROOT ORDER BY provider, key;", schema_skill)
        connection_references = {
            path.stem for path in (skill_root / "connect-warehouse" / "references").glob("*.md")
        }
        self.assertEqual(
            connection_references, {"snowflake", "bigquery", "databricks", "clickhouse"}
        )
        clickhouse_reference = (
            skill_root / "connect-warehouse" / "references" / "clickhouse.md"
        ).read_text()
        self.assertIn('password=cfg.get("password", "")', clickhouse_reference)

    def test_claude_marketplace_installs_same_plugin(self):
        marketplace = json.loads(CLAUDE_MARKETPLACE_PATH.read_text())

        self.assertEqual(marketplace["name"], "agents-schema")
        self.assertEqual(marketplace["owner"]["name"], "dbt Labs")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "agents-schema")
        self.assertEqual(entry["source"], "./plugins/agents-schema")

        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text()
        )
        self.assertEqual(manifest["name"], entry["name"])
        self.assertTrue((PLUGIN_ROOT / "skills" / "agents-schema-search" / "SKILL.md").is_file())
        self.assertTrue((PLUGIN_ROOT / "skills" / "connect-warehouse" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
