from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app import db
from app.feedback_weights import apply_feedback_score, load_feedback_weights


class FeedbackWeightsTests(unittest.TestCase):
    def test_ignore_rule_lowers_effective_score_without_overwriting_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                source_id = db.upsert_source(conn, "demo", "rss_entry", {})
                item_id = db.upsert_item(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "rss_entry",
                        "title": "娱乐 新闻",
                        "url": "https://example.com/a",
                        "content_snippet": "",
                        "raw_json": "{}",
                        "hash": "a",
                        "published_at": None,
                        "fetched_at": "2026-05-25T00:00:00+00:00",
                        "score": 88,
                        "status": "new",
                    },
                )
                db.add_ignored_rule(conn, "keyword", "娱乐")

                weights = load_feedback_weights(conn)
                effective, reasons = apply_feedback_score(88, {"title": "娱乐 新闻", "_item_id": item_id}, weights)
                stored = conn.execute("SELECT score FROM items WHERE id=?", (item_id,)).fetchone()["score"]

                self.assertLess(effective, 0)
                self.assertIn("blocked_keywords:娱乐", reasons)
                self.assertEqual(stored, 88)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
