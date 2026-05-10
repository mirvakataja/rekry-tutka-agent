from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from rekry_tutka_agent.db import DocumentStore
from rekry_tutka_agent.llm import KeywordAnalyzer, analyze_stored_documents, extract_keywords, sanitize_keywords
from rekry_tutka_agent.models import CollectedItem, StoredDocument


class FakeChatModel:
    model = "fake-model"

    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        return self.response


class KeywordAnalyzerTests(unittest.TestCase):
    def test_extract_keywords_accepts_object_payload(self) -> None:
        self.assertEqual(
            extract_keywords('{"keywords": ["AI sourcing", "Candidate experience"]}'),
            ["AI sourcing", "Candidate experience"],
        )

    def test_sanitize_keywords_deduplicates_and_limits_to_five(self) -> None:
        keywords = sanitize_keywords(
            [" AI sourcing ", "ai sourcing", "Candidate Experience", "Skills", "DEI", "Analytics"],
            max_keywords=5,
        )

        self.assertEqual(keywords, ["ai sourcing", "candidate experience", "skills", "dei", "analytics"])

    def test_keyword_analyzer_returns_keyword_analysis(self) -> None:
        analyzer = KeywordAnalyzer(FakeChatModel('{"keywords": ["AI sourcing", "Skills-based hiring"]}'))
        document = StoredDocument(
            id=42,
            title="Talent acquisition report",
            content="Teams discuss AI sourcing and skills-based hiring.",
            source_url="https://example.com/report",
            content_hash="abc123",
        )

        analysis = analyzer.analyze_document(document)

        self.assertEqual(analysis.document_id, 42)
        self.assertEqual(analysis.keywords, ("ai sourcing", "skills-based hiring"))
        self.assertEqual(analysis.model, "fake-model")
        self.assertEqual(analysis.content_hash, "abc123")

    def test_analyze_stored_documents_persists_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            with DocumentStore(database) as store:
                store.initialize()
                store.upsert_item(
                    CollectedItem(
                        source_name="Example",
                        title="Recruiting automation",
                        publication_date=None,
                        content="Recruiters discuss automation and candidate experience.",
                        source_url="https://example.com/automation",
                    )
                )

            result = analyze_stored_documents(
                database_path=str(database),
                chat_model=FakeChatModel('{"keywords": ["automation", "candidate experience"]}'),
            )

            self.assertEqual(result.documents_checked, 1)
            self.assertEqual(result.analyzed_count, 1)
            self.assertEqual(result.error_count, 0)

            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT keywords_json, model FROM document_keyword_analysis"
                ).fetchone()

        self.assertEqual(json.loads(row[0]), ["automation", "candidate experience"])
        self.assertEqual(row[1], "fake-model")


if __name__ == "__main__":
    unittest.main()
