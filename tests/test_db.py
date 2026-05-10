from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rekry_tutka_agent.db import DocumentStore
from rekry_tutka_agent.models import CollectedItem


class DocumentStoreTests(unittest.TestCase):
    def test_upsert_inserts_then_updates_changed_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            item = CollectedItem(
                source_name="Example",
                title="Talent acquisition trends",
                publication_date="2026-05-10T01:00:00+00:00",
                content="Original content",
                source_url="https://example.com/article",
            )

            with DocumentStore(database) as store:
                store.initialize()
                self.assertEqual(store.upsert_item(item), "inserted")
                self.assertEqual(store.upsert_item(item), "unchanged")
                changed = CollectedItem(
                    source_name=item.source_name,
                    title=item.title,
                    publication_date=item.publication_date,
                    content="Updated content",
                    source_url=item.source_url,
                )
                self.assertEqual(store.upsert_item(changed), "updated")

            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT title, content, source_url FROM documents"
                ).fetchone()

            self.assertEqual(row, ("Talent acquisition trends", "Updated content", "https://example.com/article"))


if __name__ == "__main__":
    unittest.main()
