from __future__ import annotations

import unittest

from app import db


class DbTests(unittest.TestCase):
    def test_item_upsert_deduplicates_repo(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                source_id = db.upsert_source(conn, "github-search", "github_repo", {})
                item = {
                    "source_id": source_id,
                    "source_type": "github_repo",
                    "title": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "content_snippet": "demo",
                    "raw_json": "{}",
                    "hash": "owner/repo",
                    "published_at": None,
                    "fetched_at": "2026-05-25T00:00:00+00:00",
                    "score": 1,
                    "status": "new",
                }
                first = db.upsert_item(conn, item)
                first_seen = conn.execute("SELECT first_seen_at FROM items WHERE id=?", (first,)).fetchone()["first_seen_at"]
                item["score"] = 2
                item["fetched_at"] = "2026-05-26T00:00:00+00:00"
                second = db.upsert_item(conn, item)
                count = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
                stored = conn.execute("SELECT score, first_seen_at, last_seen_at FROM items WHERE id=?", (first,)).fetchone()
                self.assertEqual(first, second)
                self.assertEqual(count, 1)
                self.assertEqual(stored["score"], 2)
                self.assertEqual(stored["first_seen_at"], first_seen)
                self.assertEqual(stored["last_seen_at"], "2026-05-26T00:00:00+00:00")
                self.assertGreaterEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            finally:
                conn.close()

    def test_deadline_events_crud(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                event_id = db.upsert_deadline_event(
                    conn,
                    {
                        "item_id": 1,
                        "title": "选课确认",
                        "event_type": "确认",
                        "deadline": "2026-06-05",
                        "confidence": 0.9,
                        "source_url": "https://example.com",
                        "status": "pending",
                    },
                )
                second_id = db.upsert_deadline_event(
                    conn,
                    {
                        "item_id": 1,
                        "title": "选课确认",
                        "event_type": "确认",
                        "deadline": "2026-06-05",
                        "confidence": 0.7,
                        "source_url": "https://example.com",
                        "status": "pending",
                    },
                )
                events = db.load_deadline_events(conn)

                self.assertEqual(event_id, second_id)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["confidence"], 0.7)
            finally:
                conn.close()

    def test_source_health_accumulates_runs(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                run = {
                    "source_name": "demo",
                    "source_type": "rss_entry",
                    "url": "https://example.com/feed.xml",
                    "status": "success",
                    "item_count": 3,
                    "duration_ms": 120,
                    "started_at": "2026-05-25T00:00:00+00:00",
                    "finished_at": "2026-05-25T00:00:01+00:00",
                }
                db.log_source_run(conn, run)
                run["status"] = "failed"
                run["error_message"] = "timeout"
                db.log_source_run(conn, run)
                health = db.load_source_health(conn)
                self.assertEqual(len(health), 1)
                self.assertEqual(health[0]["success_count"], 1)
                self.assertEqual(health[0]["failure_count"], 1)
                self.assertEqual(health[0]["last_status"], "failed")
                self.assertEqual(health[0]["last_error"], "timeout")
            finally:
                conn.close()

    def test_mark_items_notified_updates_selected_items(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                source_id = db.upsert_source(conn, "github-search", "github_repo", {})
                item = {
                    "source_id": source_id,
                    "source_type": "github_repo",
                    "title": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "content_snippet": "demo",
                    "raw_json": "{}",
                    "hash": "owner/repo",
                    "published_at": None,
                    "fetched_at": "2026-05-25T00:00:00+00:00",
                    "score": 1,
                    "status": "new",
                }
                item_id = db.upsert_item(conn, item)
                updated = db.mark_items_notified(conn, [item_id], "2026-05-25-08")
                stored = conn.execute("SELECT last_notified_slot FROM items WHERE id=?", (item_id,)).fetchone()
                self.assertEqual(updated, 1)
                self.assertEqual(stored["last_notified_slot"], "2026-05-25-08")
            finally:
                conn.close()

    def test_feedback_tables_support_save_ignore_and_query(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                source_id = db.upsert_source(conn, "rss", "industry_news", {})
                item_id = db.upsert_item(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "industry_news",
                        "title": "EDA verification update",
                        "url": "https://example.com/eda",
                        "content_snippet": "chip design flow",
                        "raw_json": "{}",
                        "hash": "https://example.com/eda",
                        "published_at": None,
                        "fetched_at": "2026-05-25T00:00:00+00:00",
                        "score": 88,
                        "status": "new",
                    },
                )

                found = db.find_item_by_url(conn, "https://example.com/eda")
                saved_id = db.save_item(conn, item_id, note="read later", source="test")
                rule_id = db.add_ignored_rule(conn, "keyword", "娱乐")
                queried = db.query_items(conn, keyword="verification", limit=5)
                actions = conn.execute("SELECT COUNT(*) AS c FROM user_actions").fetchone()["c"]

                self.assertEqual(found["id"], item_id)
                self.assertGreater(saved_id, 0)
                self.assertGreater(rule_id, 0)
                self.assertEqual(queried[0]["id"], item_id)
                self.assertEqual(db.load_ignored_rules(conn)[0]["pattern"], "娱乐")
                self.assertEqual(actions, 2)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
