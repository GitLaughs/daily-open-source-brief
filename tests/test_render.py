from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from app.render import markdownish_to_html, prune_archives, render_email


class RenderTests(unittest.TestCase):
    def test_markdownish_lists_are_wrapped(self):
        html = markdownish_to_html("# 标题\n\n## 小节\n- 第一条\n  详情：https://example.com\n- 第二条")
        self.assertIn('<ul class="digest-list">', html)
        self.assertEqual(html.count("<li>"), 2)
        self.assertIn("</ul>", html)
        self.assertIn('<a href="https://example.com">https://example.com</a>', html)

    def test_render_email_contains_school_and_repo_sections(self):
        html = render_email(
            date(2026, 5, 25),
            "# 今日个人日报\n\n## 今日优先处理\n- [教务处] 选课通知\n  链接：https://jwc.xjtu.edu.cn/info/1.htm",
            [
                {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                    "description": "demo",
                    "stargazers_count": 100,
                    "language": "Python",
                    "license": {"spdx_id": "MIT"},
                    "_score": 88,
                }
            ],
            "template",
            web_items=[
                {
                    "source_title": "西安交大教务处 教学通知",
                    "title": "选课通知",
                    "url": "https://jwc.xjtu.edu.cn/info/1.htm",
                    "published_at": "2026-05-25",
                    "content_snippet": "请按时处理",
                }
            ],
        )
        self.assertIn("个人技术与产业日报", html)
        self.assertIn("网页与 RSS 情报源", html)
        self.assertIn("开源项目速览", html)

    def test_prune_archives_only_deletes_old_date_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_file = root / "2026-01-01.html"
            keep_file = root / "2026-05-20.html"
            misc_file = root / "index.html"
            old_file.write_text("old", encoding="utf-8")
            keep_file.write_text("keep", encoding="utf-8")
            misc_file.write_text("misc", encoding="utf-8")

            deleted = prune_archives(root, today=date(2026, 5, 25), retention_days=30)

            self.assertEqual(deleted, [old_file])
            self.assertFalse(old_file.exists())
            self.assertTrue(keep_file.exists())
            self.assertTrue(misc_file.exists())


if __name__ == "__main__":
    unittest.main()
