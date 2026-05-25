from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app import db
from app.knowledge import search_items


def insert_item(conn, *, title: str, snippet: str, item_hash: str = "item") -> int:
    source_id = db.upsert_source(conn, "rss", "rss_entry", {})
    return db.upsert_item(
        conn,
        {
            "source_id": source_id,
            "source_type": "rss_entry",
            "title": title,
            "url": f"https://example.com/{item_hash}",
            "content_snippet": snippet,
            "raw_json": "{}",
            "hash": item_hash,
            "published_at": None,
            "fetched_at": "2026-05-25T00:00:00+00:00",
            "score": 10,
            "status": "new",
        },
    )


class FtsTests(unittest.TestCase):
    def test_upsert_item_writes_search_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                item_id = insert_item(conn, title="EDA verification update", snippet="chip design flow")

                rows = search_items(conn, "verification")

                self.assertEqual([row["id"] for row in rows], [item_id])
            finally:
                conn.close()

    def test_upsert_item_refreshes_search_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                source_id = db.upsert_source(conn, "rss", "rss_entry", {})
                item = {
                    "source_id": source_id,
                    "source_type": "rss_entry",
                    "title": "EDA verification update",
                    "url": "https://example.com/eda",
                    "content_snippet": "chip design flow",
                    "raw_json": "{}",
                    "hash": "eda",
                    "published_at": None,
                    "fetched_at": "2026-05-25T00:00:00+00:00",
                    "score": 10,
                    "status": "new",
                }
                item_id = db.upsert_item(conn, item)
                item["title"] = "Python packaging update"
                item["content_snippet"] = "wheel build backend"
                item["fetched_at"] = "2026-05-26T00:00:00+00:00"
                db.upsert_item(conn, item)

                self.assertEqual(search_items(conn, "verification"), [])
                self.assertEqual([row["id"] for row in search_items(conn, "Python")], [item_id])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
