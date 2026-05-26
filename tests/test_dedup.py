from __future__ import annotations

import unittest

from app.dedup import dedupe_cross_source


class DedupeTests(unittest.TestCase):
    def test_cross_source_title_dedupe(self):
        items = [
            {"title": "关于本科生选课确认的通知", "source_type": "school_notice"},
            {"title": "本科生选课确认通知", "source_type": "rss_entry"},
            {"title": "EDA verification update", "source_type": "industry_news"},
        ]

        deduped = dedupe_cross_source(items, threshold=0.45)

        self.assertEqual(len(deduped), 2)
        self.assertTrue(items[1]["deduped_cross_source"])


if __name__ == "__main__":
    unittest.main()
