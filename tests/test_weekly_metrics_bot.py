from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from app import db
from app.lark_bot import handle_command
from app.metrics import collect_metrics
from app.weekly_report import build_weekly_report


class WeeklyMetricsBotTests(unittest.TestCase):
    def test_weekly_metrics_and_bot_use_sqlite_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "brief.sqlite"
            conn = db.connect(db_path)
            try:
                source_id = db.upsert_source(conn, "demo", "school_notice", {})
                item_id = db.upsert_item(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "school_notice",
                        "title": "选课确认通知",
                        "url": "https://example.com/notice",
                        "content_snippet": "请按时确认",
                        "raw_json": "{}",
                        "hash": "notice",
                        "published_at": None,
                        "fetched_at": "2026-05-25T00:00:00+00:00",
                        "score": 90,
                        "status": "new",
                    },
                )
                db.save_item(conn, item_id, source="test")
                db.log_source_run(
                    conn,
                    {
                        "source_name": "demo",
                        "source_type": "school_notice",
                        "url": "https://example.com",
                        "status": "success",
                        "item_count": 1,
                        "duration_ms": 10,
                        "started_at": "2026-05-25T00:00:00+00:00",
                        "finished_at": "2026-05-25T00:00:01+00:00",
                    },
                )

                report = build_weekly_report(conn, today=date(2026, 5, 25))
                metrics = collect_metrics(conn)
                conn.commit()
            finally:
                conn.close()

            bot_reply = handle_command("/日报 搜索 选课", db_path=db_path)

            self.assertIn("选课确认通知", report)
            self.assertGreaterEqual(metrics["total_items"], 1)
            self.assertIn("选课确认通知", bot_reply)


if __name__ == "__main__":
    unittest.main()
