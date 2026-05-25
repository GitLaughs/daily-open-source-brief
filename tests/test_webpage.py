from __future__ import annotations

from datetime import date
import unittest

from app.fetch_webpage import parse_webpage_entries, score_web_entry


class WebpageFetchTests(unittest.TestCase):
    def test_parse_public_notice_list_item(self):
        html = """
        <ul>
          <li>
            <a href="../notice/1092/10213.htm" title="[Notice] Summer school application deadline">
              [Notice] Summer school application deadline
            </a>
            <span>2026-05-22</span>
          </li>
        </ul>
        """
        source = {
            "name": "example-public",
            "title": "Example Campus Notices",
            "url_allow_patterns": ["/notice/"],
            "priority_keywords": ["application", "deadline"],
        }
        entries = parse_webpage_entries(html, "https://example.edu/notices/index.htm", source, today=date(2026, 5, 25))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["published_at"], "2026-05-22")
        self.assertEqual(entries[0]["url"], "https://example.edu/notice/1092/10213.htm")
        self.assertIn("Summer school", entries[0]["title"])
        self.assertGreater(entries[0]["_score"], 90)

    def test_parse_student_affairs_compact_date(self):
        html = """
        <li>
          <span><b>19</b><i>2026/05</i></span>
          <a href="../notice/1060/16552.htm" title="Graduate funding application reminder">
            <h2>Graduate funding application reminder</h2>
            <p>Applicants should submit materials before the deadline.</p>
          </a>
        </li>
        """
        source = {"name": "example-public", "title": "Example Public Notices", "url_allow_patterns": ["/notice/"]}
        entries = parse_webpage_entries(html, "https://example.edu/notices/index.htm", source, today=date(2026, 5, 25))
        self.assertEqual(entries[0]["published_at"], "2026-05-19")
        self.assertEqual(entries[0]["title"], "Graduate funding application reminder")
        self.assertIn("submit materials", entries[0]["content_snippet"])

    def test_score_prioritizes_action_keywords(self):
        source = {"priority_keywords": ["registration"], "weight": 5}
        entry = {
            "title": "Course registration confirmation notice",
            "content_snippet": "",
            "published_at": "2026-05-25",
        }
        self.assertGreater(score_web_entry(entry, source, today=date(2026, 5, 25)), 90)


if __name__ == "__main__":
    unittest.main()
