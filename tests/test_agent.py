from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rekry_tutka_agent.agent import TalentAcquisitionAgent
from rekry_tutka_agent.models import SourceConfig


class FakeFetcher:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def fetch_text(self, url: str) -> str:
        return self.responses[url]


class TalentAcquisitionAgentTests(unittest.TestCase):
    def test_agent_collects_feed_items_enriches_content_and_stores_them(self) -> None:
        feed_url = "https://example.com/feed.xml"
        article_url = "https://example.com/article"
        feed = f"""<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Talent acquisition trend report</title>
              <link>{article_url}</link>
              <pubDate>Sun, 10 May 2026 01:00:00 +0000</pubDate>
              <description>Short feed summary.</description>
            </item>
          </channel>
        </rss>
        """
        article = """<!doctype html>
        <html>
          <head>
            <title>Article title from page</title>
            <meta property="article:published_time" content="2026-05-10T02:00:00Z">
          </head>
          <body>
            <article>
              <h1>Talent acquisition trend report</h1>
              <p>Longer article body about candidate experience and AI.</p>
            </article>
          </body>
        </html>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            agent = TalentAcquisitionAgent(
                sources=[SourceConfig(name="Example", url=feed_url)],
                database_path=database,
                fetcher=FakeFetcher({feed_url: feed, article_url: article}),
            )

            result = agent.run()

            self.assertEqual(result.items_seen, 1)
            self.assertEqual(result.inserted_count, 1)
            self.assertEqual(result.error_count, 0)

            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    "SELECT title, publication_date, content, source_url FROM documents"
                ).fetchone()

        self.assertEqual(row[0], "Talent acquisition trend report")
        self.assertEqual(row[1], "2026-05-10T01:00:00+00:00")
        self.assertIn("Longer article body", row[2])
        self.assertEqual(row[3], article_url)

    def test_agent_can_store_feed_content_without_fetching_links(self) -> None:
        feed_url = "https://example.com/feed.xml"
        article_url = "https://example.com/discussion"
        feed = f"""<rss><channel><item>
          <title>Recruiting discussion</title>
          <link>{article_url}</link>
          <description>Discussion content from feed.</description>
        </item></channel></rss>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            agent = TalentAcquisitionAgent(
                sources=[SourceConfig(name="Discussion", url=feed_url, fetch_content=False)],
                database_path=database,
                fetcher=FakeFetcher({feed_url: feed}),
            )

            result = agent.run()

            self.assertEqual(result.inserted_count, 1)

            with sqlite3.connect(database) as connection:
                content = connection.execute("SELECT content FROM documents").fetchone()[0]

        self.assertEqual(content, "Discussion content from feed.")


if __name__ == "__main__":
    unittest.main()
