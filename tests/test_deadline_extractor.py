from __future__ import annotations

from datetime import date
import unittest

from app.deadline_extractor import extract_deadlines


class DeadlineExtractorTests(unittest.TestCase):
    def test_extract_full_date_deadline(self):
        events = extract_deadlines(
            "关于选课确认截止 2026年6月5日的通知",
            "",
            today=date(2026, 5, 25),
            source_url="https://example.com/1",
            item_id=1,
        )

        self.assertEqual(events[0].deadline.isoformat(), "2026-06-05")
        self.assertEqual(events[0].event_type, "确认")
        self.assertEqual(events[0].status, "pending")
        self.assertGreaterEqual(events[0].confidence, 0.9)

    def test_extract_month_day_time(self):
        events = extract_deadlines("答辩安排", "答辩时间：6月10日 上午8:30", today=date(2026, 5, 25))

        self.assertEqual(events[0].deadline.isoformat(), "2026-06-10")
        self.assertEqual(events[0].event_type, "答辩")
        self.assertEqual(events[0].confidence, 0.5)

    def test_expired_is_marked(self):
        events = extract_deadlines("报名截止 2026年5月1日", "", today=date(2026, 5, 25))

        self.assertEqual(events[0].status, "expired")
        self.assertEqual(events[0].confidence, 0.1)


if __name__ == "__main__":
    unittest.main()
