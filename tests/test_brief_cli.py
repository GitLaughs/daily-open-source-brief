from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import brief_cli, db
from app.config import default_paths


class BriefCliTests(unittest.TestCase):
    def test_search_and_save_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = replace(
                default_paths(root),
                db=root / "brief.sqlite",
                data_dir=root,
                archive_dir=root / "archive",
                log_dir=root / "logs",
            )
            conn = db.connect(paths.db)
            try:
                source_id = db.upsert_source(conn, "rss", "industry_news", {})
                db.upsert_item(
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
                conn.commit()
            finally:
                conn.close()

            with patch("app.brief_cli.default_paths", return_value=paths):
                out = StringIO()
                with redirect_stdout(out):
                    self.assertEqual(brief_cli.main(["search", "verification"]), 0)
                self.assertIn("EDA verification update", out.getvalue())

                out = StringIO()
                with redirect_stdout(out):
                    self.assertEqual(brief_cli.main(["save", "--url", "https://example.com/eda", "--note", "later"]), 0)
                self.assertIn("Saved item", out.getvalue())

            conn = db.connect(paths.db)
            try:
                saved = conn.execute("SELECT note FROM saved_items").fetchone()
                self.assertEqual(saved["note"], "later")
            finally:
                conn.close()

    def test_ignore_command_adds_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = replace(default_paths(root), db=root / "brief.sqlite", data_dir=root)
            with patch("app.brief_cli.default_paths", return_value=paths):
                out = StringIO()
                with redirect_stdout(out):
                    self.assertEqual(brief_cli.main(["ignore", "--keyword", "娱乐"]), 0)
            self.assertIn("keyword=娱乐", out.getvalue())

            conn = db.connect(paths.db)
            try:
                rules = db.load_ignored_rules(conn)
                self.assertEqual(rules[0]["pattern"], "娱乐")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
