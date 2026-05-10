from __future__ import annotations

import unittest

from rekry_tutka_agent.models import SourceConfig
from rekry_tutka_agent.parsers import parse_feed


class ParseFeedTests(unittest.TestCase):
    def test_parses_rss_item(self) -> None:
        xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Talent acquisition trends in 2026</title>
              <link>https://example.com/trends</link>
              <pubDate>Sun, 10 May 2026 01:00:00 +0000</pubDate>
              <description><![CDATA[<p>AI and skills-based hiring are discussed.</p>]]></description>
            </item>
          </channel>
        </rss>
        """

        items = parse_feed(xml, SourceConfig(name="Example", url="https://example.com/rss"))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Talent acquisition trends in 2026")
        self.assertEqual(items[0].source_url, "https://example.com/trends")
        self.assertEqual(items[0].publication_date, "2026-05-10T01:00:00+00:00")
        self.assertEqual(items[0].content, "AI and skills-based hiring are discussed.")

    def test_parses_atom_entry_link_href(self) -> None:
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Recruiting community discussion</title>
            <link href="https://example.com/discussion" rel="alternate" />
            <updated>2026-05-10T01:00:00Z</updated>
            <summary>Practitioners compare sourcing strategies.</summary>
          </entry>
        </feed>
        """

        items = parse_feed(xml, SourceConfig(name="Atom", url="https://example.com/atom"))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_url, "https://example.com/discussion")
        self.assertEqual(items[0].content, "Practitioners compare sourcing strategies.")

    def test_skips_entries_without_title_or_link(self) -> None:
        xml = """<rss><channel><item><title>No link</title></item></channel></rss>"""

        items = parse_feed(xml, SourceConfig(name="Example", url="https://example.com/rss"))

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
