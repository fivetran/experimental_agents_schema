import unittest

from agents_schema.root import ROOT, ROOT_ENTRIES, upsert_provider_root


class FakeDestination:
    def __init__(self):
        self.upserts = []

    def upsert_rows(self, table, rows):
        self.upserts.append((table, list(rows)))


class RootTests(unittest.TestCase):
    def test_root_content_uses_portable_canonical_table_names(self):
        content = "\n".join(
            entry_content
            for entries in ROOT_ENTRIES.values()
            for _, entry_content in entries
        )

        self.assertNotIn("AGENTS.", content)

    def test_upsert_provider_root_writes_only_requested_provider(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "dbt")

        self.assertEqual(len(dest.upserts), 1)
        table, rows = dest.upserts[0]
        self.assertIs(table, ROOT)
        self.assertTrue(rows)
        self.assertEqual({row[0] for row in rows}, {"dbt"})
        self.assertEqual({row[1] for row in rows}, {"overview", "model", "column", "dependency"})

    def test_upsert_provider_root_has_osi_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "osi")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview", "model", "dataset", "field", "metric", "relationship"})

    def test_upsert_provider_root_has_lookml_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "lookml")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview", "view", "dimension", "measure", "explore"})

    def test_upsert_provider_root_has_omni_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "omni")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview", "view", "dimension", "measure", "topic", "topic_join"})

    def test_upsert_provider_root_has_skills_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "skills")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview", "root-convention", "skill_use"})

    def test_upsert_provider_root_has_snowflake_semantic_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "snowflake_semantic")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview"})
        self.assertEqual({row[0] for row in rows}, {"snowflake_semantic"})

    def test_upsert_provider_root_has_sigma_entries(self):
        dest = FakeDestination()

        upsert_provider_root(dest, "sigma")

        _, rows = dest.upserts[0]
        self.assertEqual({row[1] for row in rows}, {"overview", "data_model", "element", "column", "metric"})
        self.assertEqual({row[0] for row in rows}, {"sigma"})


if __name__ == "__main__":
    unittest.main()
