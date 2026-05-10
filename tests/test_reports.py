from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from rekry_tutka_agent.db import DocumentStore
from rekry_tutka_agent.models import CollectedItem, KeywordAnalysis
from rekry_tutka_agent.reports import build_weekly_keyword_report, format_keyword_report_html, format_keyword_report_table


class WeeklyKeywordReportTests(unittest.TestCase):
    def test_report_counts_keywords_and_limits_occurrence_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            with DocumentStore(database) as store:
                store.initialize()
                for index, keywords in enumerate(
                    [
                        ("ai sourcing", "candidate experience"),
                        ("ai sourcing",),
                        ("ai sourcing", "analytics"),
                    ],
                    start=1,
                ):
                    store.upsert_item(
                        CollectedItem(
                            source_name="Example",
                            title=f"Article {index}",
                            publication_date=None,
                            content=f"Content {index}",
                            source_url=f"https://example.com/{index}",
                        )
                    )
                    document = store.documents_for_keyword_analysis(force=True)[-1]
                    store.save_keyword_analysis(
                        KeywordAnalysis(
                            document_id=document.id,
                            keywords=keywords,
                            model="test-model",
                            prompt_version="test-v1",
                            content_hash=document.content_hash,
                        )
                    )

            rows = build_weekly_keyword_report(
                database_path=str(database),
                now=datetime.now(timezone.utc),
                top_n=2,
                links_per_keyword=2,
            )

        self.assertEqual(rows[0].keyword, "ai sourcing")
        self.assertEqual(rows[0].count, 3)
        self.assertEqual(len(rows[0].occurrence_links), 2)
        self.assertEqual(rows[0].occurrence_links[0].source_name, "Example")
        self.assertEqual(rows[1].count, 1)

    def test_report_formats_empty_table(self) -> None:
        table = format_keyword_report_table([])

        self.assertIn("| Avainsana | Esiintymat | Esimerkkilinkit |", table)
        self.assertIn("| Ei tuloksia | 0 | |", table)

    def test_report_formats_html_table_with_active_title_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            with DocumentStore(database) as store:
                store.initialize()
                store.upsert_item(
                    CollectedItem(
                        source_name="Example Source",
                        title="Recruiting analytics report",
                        publication_date=None,
                        content="Analytics content",
                        source_url="https://example.com/report",
                    )
                )
                document = store.documents_for_keyword_analysis(force=True)[0]
                store.save_keyword_analysis(
                    KeywordAnalysis(
                        document_id=document.id,
                        keywords=("analytics",),
                        model="test-model",
                        prompt_version="test-v1",
                        content_hash=document.content_hash,
                    )
                )

            rows = build_weekly_keyword_report(
                database_path=str(database),
                now=datetime.now(timezone.utc),
            )

        html = format_keyword_report_html(rows)

        self.assertIn("<table>", html)
        self.assertIn('<a href="https://example.com/report">Recruiting analytics report (Example Source)</a>', html)
        self.assertNotIn(">https://example.com/report<", html)


if __name__ == "__main__":
    unittest.main()
