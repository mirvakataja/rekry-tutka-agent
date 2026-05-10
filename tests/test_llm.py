from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from rekry_tutka_agent.db import DocumentStore
from rekry_tutka_agent.llm import (
    KeywordAnalyzer,
    analyze_stored_documents,
    extract_keywords,
    extract_trends,
    sanitize_keywords,
    sanitize_trends,
    summarize_weekly_trends,
)
from rekry_tutka_agent.models import CollectedItem, KeywordAnalysis, StoredDocument


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

    def test_extract_trends_accepts_object_payload(self) -> None:
        self.assertEqual(
            extract_trends('{"trends": ["Skills-based hiring grows", "AI sourcing matures"]}'),
            ["Skills-based hiring grows", "AI sourcing matures"],
        )

    def test_sanitize_keywords_deduplicates_and_limits_to_five(self) -> None:
        keywords = sanitize_keywords(
            [" AI sourcing ", "ai sourcing", "Candidate Experience", "Skills", "DEI", "Analytics"],
            max_keywords=5,
        )

        self.assertEqual(keywords, ["ai sourcing", "candidate experience", "skills", "dei", "analytics"])

    def test_sanitize_trends_deduplicates_and_limits_to_five(self) -> None:
        trends = sanitize_trends(
            [" AI sourcing matures ", "AI sourcing matures", "Skills signals rise", "Analytics", "DEI", "Internal mobility"],
            max_bullets=5,
        )

        self.assertEqual(
            trends,
            ["AI sourcing matures", "Skills signals rise", "Analytics", "DEI", "Internal mobility"],
        )

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

    def test_summarize_weekly_trends_uses_keyword_report_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            with DocumentStore(database) as store:
                store.initialize()
                store.upsert_item(
                    CollectedItem(
                        source_name="Example",
                        title="Skills-based hiring report",
                        publication_date=None,
                        content="Skills content",
                        source_url="https://example.com/skills",
                    )
                )
                document = store.documents_for_keyword_analysis(force=True)[0]
                store.save_keyword_analysis(
                    KeywordAnalysis(
                        document_id=document.id,
                        keywords=("skills-based hiring", "workforce analytics"),
                        model="test-model",
                        prompt_version="test-v1",
                        content_hash=document.content_hash,
                    )
                )
            chat_model = FakeChatModel(
                '{"trends": ["Osaamispohjainen rekrytointi korostuu.", "Analytiikka ohjaa rekrytointia."]}'
            )

            trends = summarize_weekly_trends(database_path=str(database), chat_model=chat_model)

        self.assertEqual(
            trends,
            ("Osaamispohjainen rekrytointi korostuu.", "Analytiikka ohjaa rekrytointia."),
        )
        self.assertIn("skills-based hiring", chat_model.messages[0][1]["content"])

    def test_summarize_weekly_trends_accepts_focus_area(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            with DocumentStore(database) as store:
                store.initialize()
                store.upsert_item(
                    CollectedItem(
                        source_name="Example",
                        title="Tech recruiting report",
                        publication_date=None,
                        content="Tech recruiting content",
                        source_url="https://example.com/tech",
                    )
                )
                document = store.documents_for_keyword_analysis(force=True)[0]
                store.save_keyword_analysis(
                    KeywordAnalysis(
                        document_id=document.id,
                        keywords=("developer hiring",),
                        model="test-model",
                        prompt_version="test-v1",
                        content_hash=document.content_hash,
                    )
                )
            chat_model = FakeChatModel('{"trends": ["Tech-rekrytointi painottuu osaamissignaaleihin."]}')

            summarize_weekly_trends(
                database_path=str(database),
                chat_model=chat_model,
                focus_area="tech/IT alan rekrytointi",
            )

        self.assertIn("tech/IT alan rekrytointi", chat_model.messages[0][1]["content"])


if __name__ == "__main__":
    unittest.main()
