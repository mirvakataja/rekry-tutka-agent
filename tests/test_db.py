from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rekry_tutka_agent.db import DocumentStore
from rekry_tutka_agent.models import CollectedItem, KeywordAnalysis


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

    def test_keyword_analysis_is_selected_until_content_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            item = CollectedItem(
                source_name="Example",
                title="Talent acquisition trends",
                publication_date=None,
                content="Candidates discuss AI sourcing.",
                source_url="https://example.com/article",
            )

            with DocumentStore(database) as store:
                store.initialize()
                store.upsert_item(item)
                documents = store.documents_for_keyword_analysis()
                self.assertEqual(len(documents), 1)

                store.save_keyword_analysis(
                    KeywordAnalysis(
                        document_id=documents[0].id,
                        keywords=("ai sourcing", "candidate experience"),
                        model="test-model",
                        prompt_version="test-v1",
                        content_hash=documents[0].content_hash,
                    )
                )
                self.assertEqual(store.documents_for_keyword_analysis(), [])
                self.assertEqual(len(store.documents_for_keyword_analysis(force=True)), 1)

            with sqlite3.connect(database) as connection:
                keywords_json = connection.execute(
                    "SELECT keywords_json FROM document_keyword_analysis"
                ).fetchone()[0]

            self.assertEqual(keywords_json, '["ai sourcing", "candidate experience"]')

    def test_scheduled_task_state_can_be_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"

            with DocumentStore(database) as store:
                store.initialize()
                self.assertIsNone(store.task_last_finished_at("daily-ingestion"))
                store.mark_task_started("daily-ingestion")
                store.mark_task_finished("daily-ingestion", "completed")
                last_finished = store.task_last_finished_at("daily-ingestion")

            self.assertIsNotNone(last_finished)


if __name__ == "__main__":
    unittest.main()
