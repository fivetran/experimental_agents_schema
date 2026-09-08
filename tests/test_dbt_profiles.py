import tempfile
import textwrap
import unittest
from pathlib import Path

from agents_schema.config import ConfigError
from agents_schema.dbt_profiles import dbt_adapter_package_from_profiles_file


class DbtProfilesTests(unittest.TestCase):
    def test_adapter_package_matches_profile_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles_path = Path(tmp) / "profiles.yml"
            profiles_path.write_text(
                textwrap.dedent(
                    """
                    analytics:
                      outputs:
                        snowflake:
                          type: snowflake
                        databricks:
                          type: databricks
                        bigquery:
                          type: bigquery
                        clickhouse:
                          type: clickhouse
                    """
                ).strip()
            )

            self.assertEqual(
                dbt_adapter_package_from_profiles_file(profiles_path, "analytics", "snowflake"),
                "dbt-snowflake",
            )
            self.assertEqual(
                dbt_adapter_package_from_profiles_file(profiles_path, "analytics", "databricks"),
                "dbt-databricks",
            )
            self.assertEqual(
                dbt_adapter_package_from_profiles_file(profiles_path, "analytics", "bigquery"),
                "dbt-bigquery",
            )
            self.assertEqual(
                dbt_adapter_package_from_profiles_file(profiles_path, "analytics", "clickhouse"),
                "dbt-clickhouse",
            )

    def test_adapter_package_normalizes_profile_type_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles_path = Path(tmp) / "profiles.yml"
            profiles_path.write_text(
                textwrap.dedent(
                    """
                    analytics:
                      target: prod
                      outputs:
                        prod:
                          type: BigQuery
                    """
                ).strip()
            )

            self.assertEqual(
                dbt_adapter_package_from_profiles_file(profiles_path, "analytics"),
                "dbt-bigquery",
            )

    def test_adapter_package_error_lists_supported_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles_path = Path(tmp) / "profiles.yml"
            profiles_path.write_text(
                textwrap.dedent(
                    """
                    analytics:
                      target: prod
                      outputs:
                        prod:
                          type: postgres
                    """
                ).strip()
            )

            with self.assertRaisesRegex(
                ConfigError,
                "supported types: bigquery, clickhouse, databricks, snowflake",
            ):
                dbt_adapter_package_from_profiles_file(profiles_path, "analytics")


if __name__ == "__main__":
    unittest.main()
