from __future__ import annotations

from datetime import date
import unittest

from app.fetch_rss import parse_feed_date, parse_rss_entries


class RssFetchTests(unittest.TestCase):
    def test_parse_rss_feed_items(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Demo Feed</title>
            <item>
              <title>EDA verification chip update</title>
              <link>https://example.com/news/1</link>
              <guid>news-1</guid>
              <pubDate>Mon, 25 May 2026 08:00:00 GMT</pubDate>
              <description><![CDATA[New semiconductor verification flow.]]></description>
            </item>
          </channel>
        </rss>
        """
        entries = parse_rss_entries(
            xml,
            {
                "name": "demo",
                "title": "Demo RSS",
                "source_type": "industry_news",
                "priority_keywords": ["verification"],
            },
            today=date(2026, 5, 25),
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["published_at"], "2026-05-25")
        self.assertEqual(entries[0]["url"], "https://example.com/news/1")
        self.assertGreater(entries[0]["_score"], 80)

    def test_parse_atom_feed_items(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Analog circuit design note</title>
            <link href="https://example.com/atom/1" />
            <id>atom-1</id>
            <updated>2026-05-24T10:00:00Z</updated>
            <summary>Useful analog and power topic.</summary>
          </entry>
        </feed>
        """
        entries = parse_rss_entries(xml, {"name": "atom", "title": "Atom"}, today=date(2026, 5, 25))
        self.assertEqual(entries[0]["published_at"], "2026-05-24")
        self.assertEqual(entries[0]["url"], "https://example.com/atom/1")

    def test_parse_feed_date(self):
        self.assertEqual(parse_feed_date("Mon, 25 May 2026 08:00:00 GMT"), "2026-05-25")


if __name__ == "__main__":
    unittest.main()
