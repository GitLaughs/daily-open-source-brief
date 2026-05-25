from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import db
from app.cli import main
from app.config import default_paths, load_yaml_config


class CliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        out = StringIO()
        with redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def test_plugin_enable_disable_updates_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "plugins.yml"
            config.write_text("plugins:\n  rss:\n    enabled: true\n", encoding="utf-8")

            disable_code, _ = self.run_cli(["plugin", "disable", "rss", "--plugins-config", str(config)])
            disabled = load_yaml_config(config)
            enable_code, _ = self.run_cli(["plugin", "enable", "rss", "--plugins-config", str(config)])
            enabled = load_yaml_config(config)

            self.assertEqual(disable_code, 0)
            self.assertFalse(disabled["plugins"]["rss"]["enabled"])
            self.assertEqual(enable_code, 0)
            self.assertTrue(enabled["plugins"]["rss"]["enabled"])

    def test_plugin_check_accepts_default_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "plugins.yml"
            config.write_text(
                """
plugins:
  github:
    enabled: true
    kind: collector
""".strip(),
                encoding="utf-8",
            )

            code, output = self.run_cli(["plugin", "check", "--plugins-config", str(config)])

            self.assertEqual(code, 0)
            self.assertIn("Plugin config OK", output)

    def test_plugin_check_rejects_bad_enabled_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "plugins.yml"
            config.write_text("plugins:\n  rss:\n    enabled: yes please\n", encoding="utf-8")

            code, output = self.run_cli(["plugin", "check", "--plugins-config", str(config)])

            self.assertEqual(code, 1)
            self.assertIn("enabled must be true or false", output)

    def test_kb_search_mark_tag_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = replace(default_paths(root), db=root / "brief.sqlite", data_dir=root)
            conn = db.connect(paths.db)
            try:
                source_id = db.upsert_source(conn, "rss", "rss_entry", {})
                item_id = db.upsert_item(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "rss_entry",
                        "title": "Python packaging update",
                        "url": "https://example.com/python",
                        "content_snippet": "wheel build backend",
                        "raw_json": "{}",
                        "hash": "python",
                        "published_at": None,
                        "fetched_at": "2026-05-25T00:00:00+00:00",
                        "score": 42,
                        "status": "new",
                    },
                )
                conn.commit()
            finally:
                conn.close()

            with patch("app.cli.default_paths", return_value=paths):
                search_code, search_output = self.run_cli(["kb", "search", "Python"])
                mark_code, mark_output = self.run_cli(["kb", "mark", str(item_id), "favorite"])
                tag_code, tag_output = self.run_cli(["kb", "tag", str(item_id), "open-eda"])
                saved_code, saved_output = self.run_cli(["kb", "saved"])

            self.assertEqual(search_code, 0)
            self.assertIn("Python packaging update", search_output)
            self.assertEqual(mark_code, 0)
            self.assertIn(f"marked {item_id} favorite=yes", mark_output)
            self.assertEqual(tag_code, 0)
            self.assertIn(f"tagged {item_id} open-eda", tag_output)
            self.assertEqual(saved_code, 0)
            self.assertIn("marks=favorite", saved_output)
            self.assertIn("tags=open-eda", saved_output)


if __name__ == "__main__":
    unittest.main()
