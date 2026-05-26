from __future__ import annotations

from datetime import date
import unittest

from app.fetch_webpage import parse_webpage_entries, score_web_entry


class WebpageFetchTests(unittest.TestCase):
    def test_parse_xjtu_notice_list_item(self):
        html = """
        <ul>
          <li>
            <a href="../info/1092/10213.htm" title="[综合通知] 关于举行无界学堂-西交通全球暑期学校项目申报的通知">
              [综合通知] 关于举行无界学堂-西交通全球暑期学校项目申报的通知
            </a>
            <span>2026-05-22</span>
          </li>
        </ul>
        """
        source = {
            "name": "xjtu-jwc",
            "title": "西安交大教务处 教学通知",
            "url_allow_patterns": ["/info/"],
            "priority_keywords": ["申报", "暑期学校"],
        }
        entries = parse_webpage_entries(html, "https://jwc.xjtu.edu.cn/jxxx/jxtz2.htm", source, today=date(2026, 5, 25))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["published_at"], "2026-05-22")
        self.assertEqual(entries[0]["url"], "https://jwc.xjtu.edu.cn/info/1092/10213.htm")
        self.assertIn("暑期学校", entries[0]["title"])
        self.assertGreater(entries[0]["_score"], 90)

    def test_parse_student_affairs_compact_date(self):
        html = """
        <li>
          <span><b>19</b><i>2026/05</i></span>
          <a href="../info/1060/16552.htm" title="关于做好2026年毕业生基层就业学费补偿工作的通知">
            <h2>关于做好2026年毕业生基层就业学费补偿工作的通知</h2>
            <p>各书院、学院，2026年毕业生：请按时办理。</p>
          </a>
        </li>
        """
        source = {"name": "xjtu-xsc", "title": "西安交大学工部 通知公告", "url_allow_patterns": ["/info/"]}
        entries = parse_webpage_entries(html, "https://xsc.xjtu.edu.cn/xgdt/tzgg.htm", source, today=date(2026, 5, 25))
        self.assertEqual(entries[0]["published_at"], "2026-05-19")
        self.assertEqual(entries[0]["title"], "关于做好2026年毕业生基层就业学费补偿工作的通知")
        self.assertIn("请按时办理", entries[0]["content_snippet"])

    def test_score_prioritizes_action_keywords(self):
        source = {"priority_keywords": ["选课"]}
        entry = {
            "title": "关于本科生选课确认的通知",
            "content_snippet": "",
            "published_at": "2026-05-25",
        }
        self.assertGreater(score_web_entry(entry, source, today=date(2026, 5, 25)), 90)


if __name__ == "__main__":
    unittest.main()
