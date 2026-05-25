from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app import db, knowledge


def add_item(conn, *, title: str = "EDA verification update", source_type: str = "industry_news") -> int:
    source_id = db.upsert_source(conn, "source", source_type, {})
    return db.upsert_item(
        conn,
        {
            "source_id": source_id,
            "source_type": source_type,
            "title": title,
            "url": "https://example.com/eda",
            "content_snippet": "chip design flow",
            "raw_json": "{}",
            "hash": title.lower().replace(" ", "-"),
            "published_at": None,
            "fetched_at": "2026-05-25T00:00:00+00:00",
            "score": 88,
            "status": "new",
        },
    )


class KnowledgeTests(unittest.TestCase):
    def test_mark_item_overwrites_existing_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                item_id = add_item(conn)

                knowledge.mark_item(conn, item_id, "favorite", source="test")
                knowledge.mark_item(conn, item_id, "favorite", value=False, source="test")

                rows = conn.execute("SELECT value FROM item_feedback WHERE item_id=?", (item_id,)).fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["value"], 0)
            finally:
                conn.close()

    def test_tag_item_does_not_duplicate_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                item_id = add_item(conn)

                knowledge.tag_item(conn, item_id, "open-eda", source="test")
                knowledge.tag_item(conn, item_id, "open-eda", source="test")

                rows = conn.execute("SELECT tag FROM item_tags WHERE item_id=?", (item_id,)).fetchall()
                self.assertEqual([row["tag"] for row in rows], ["open-eda"])
            finally:
                conn.close()

    def test_list_saved_items_reads_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                item_id = add_item(conn)
                knowledge.mark_item(conn, item_id, "later", source="test")

                rows = knowledge.list_saved_items(conn)

                self.assertEqual([row["id"] for row in rows], [item_id])
                self.assertTrue(rows[0]["feedback"]["later"])
            finally:
                conn.close()

    def test_feedback_sorting_hints_exposes_future_rank_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                item_id = add_item(conn, source_type="rss_entry")
                knowledge.tag_item(conn, item_id, "open-eda", source="test")
                knowledge.mark_item(conn, item_id, "favorite", source="test")
                knowledge.mark_item(conn, item_id, "not_interested", source="test")
                db.add_ignored_rule(conn, "keyword", "娱乐")

                hints = knowledge.feedback_sorting_hints(conn)

                self.assertEqual(hints["favorite_tags"], ["open-eda"])
                self.assertEqual(hints["blocked_keywords"], ["娱乐"])
                self.assertEqual(hints["disliked_sources"], ["rss_entry"])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
