from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import db
from app.config import Paths
from app.plugins.base import BasePlugin, PluginContext, PluginResult
from app.plugins.builtins import DeadlineEnricherPlugin, GithubCollectorPlugin, LarkSenderPlugin, builtin_registry
from app.plugins.local_loader import load_local_plugins
from app.plugins.manager import PluginManager, load_plugin_settings
from app.plugins.registry import PluginRegistry


class DummyPlugin(BasePlugin):
    name = "dummy"
    kind = "collector"

    def run(self, ctx: PluginContext) -> PluginResult:
        ctx.state["ran"] = True
        return PluginResult(self.name, self.kind)


class PluginTests(unittest.TestCase):
    def test_load_plugin_settings_merges_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugins.yml"
            path.write_text(
                """
plugins:
  rss:
    enabled: false
  github:
    limit: 2
""".strip(),
                encoding="utf-8",
            )

            settings = load_plugin_settings(path)

            self.assertFalse(settings["rss"]["enabled"])
            self.assertTrue(settings["github"]["enabled"])
            self.assertEqual(settings["github"]["limit"], 2)
            self.assertIn("renderer", settings)
            self.assertIn("deadline", settings)

    def test_manager_skips_disabled_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                paths = Paths(
                    root=Path(tmp),
                    config=Path(tmp) / "sources.yml",
                    plugins=Path(tmp) / "plugins.yml",
                    data_dir=Path(tmp),
                    db=Path(tmp) / "brief.sqlite",
                    archive_dir=Path(tmp) / "archive",
                    log_dir=Path(tmp) / "logs",
                )
                ctx = PluginContext(conn, paths, {}, date(2026, 5, 25), {}, {})
                manager = PluginManager({"dummy": {"enabled": False}})
                manager.register(DummyPlugin())

                results = manager.run_stage("collector", ctx)

                self.assertEqual(results, [])
                self.assertNotIn("ran", ctx.state)
            finally:
                conn.close()

    def test_github_collector_plugin_uses_sample_and_writes_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = db.connect(root / "brief.sqlite")
            try:
                paths = Paths(
                    root=root,
                    config=root / "sources.yml",
                    plugins=root / "plugins.yml",
                    data_dir=root,
                    db=root / "brief.sqlite",
                    archive_dir=root / "archive",
                    log_dir=root / "logs",
                )
                source_config = {
                    "github": {"queries": []},
                    "topics": {"include": ["ai", "self-hosted", "developer-tools"]},
                    "languages": {"include": ["Rust", "Go"]},
                }
                ctx = PluginContext(
                    conn,
                    paths,
                    source_config,
                    date(2026, 5, 25),
                    {"sample": True},
                    {"item_ids": []},
                )

                result = GithubCollectorPlugin({"limit": 2}).run(ctx)

                self.assertEqual(result.item_count, 2)
                self.assertEqual(len(ctx.state["ranked_repos"]), 2)
                self.assertEqual(len(ctx.state["item_ids"]), 2)
                self.assertTrue(all("_item_id" in repo for repo in ctx.state["ranked_repos"]))
                count = conn.execute("SELECT COUNT(*) AS c FROM items WHERE source_type='github_repo'").fetchone()["c"]
                self.assertEqual(count, 2)
            finally:
                conn.close()

    def test_lark_important_mode_marks_only_selected_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = db.connect(root / "brief.sqlite")
            try:
                paths = Paths(
                    root=root,
                    config=root / "sources.yml",
                    plugins=root / "plugins.yml",
                    data_dir=root,
                    db=root / "brief.sqlite",
                    archive_dir=root / "archive",
                    log_dir=root / "logs",
                )
                source_id = db.upsert_source(conn, "github-search", "github_repo", {})
                high_id = db.upsert_item(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "github_repo",
                        "title": "owner/high",
                        "url": "https://github.com/owner/high",
                        "content_snippet": "",
                        "raw_json": "{}",
                        "hash": "owner/high",
                        "published_at": None,
                        "fetched_at": "2026-05-25T00:00:00+00:00",
                        "score": 90,
                        "status": "new",
                    },
                )
                low_id = db.upsert_item(
                    conn,
                    {
                        "source_id": source_id,
                        "source_type": "github_repo",
                        "title": "owner/low",
                        "url": "https://github.com/owner/low",
                        "content_snippet": "",
                        "raw_json": "{}",
                        "hash": "owner/low",
                        "published_at": None,
                        "fetched_at": "2026-05-25T00:00:00+00:00",
                        "score": 10,
                        "status": "new",
                    },
                )
                digest_id = db.save_digest(conn, "2026-05-25-08", "title", "text", "<p>text</p>", [high_id, low_id])
                ctx = PluginContext(
                    conn,
                    paths,
                    {},
                    date(2026, 5, 25),
                    {"force_send": True, "lark_only_important": True},
                    {
                        "delivery_slot": "2026-05-25-08",
                        "subject": "开源日报 2026-05-25-08",
                        "title": "开源日报 2026-05-25",
                        "text_content": "full",
                        "archive_path": root / "archive.html",
                        "digest_id": digest_id,
                        "item_ids": [high_id, low_id],
                        "ranked_repos": [
                            {"full_name": "owner/high", "_score": 90, "_item_id": high_id},
                            {"full_name": "owner/low", "_score": 10, "_item_id": low_id},
                        ],
                        "web_items": [],
                        "source_errors": [],
                    },
                )
                with patch("app.plugins.builtins.lark_configured", return_value=True):
                    with patch("app.plugins.builtins.lark_receive_id", return_value="ou_demo"):
                        with patch("app.plugins.builtins.build_digest", return_value=("important", "template")):
                            with patch("app.plugins.builtins.send_lark_message", return_value={"message_id": "om_1"}):
                                result = LarkSenderPlugin().run(ctx)

                self.assertEqual(result.status, "success")
                rows = conn.execute(
                    "SELECT id, last_notified_slot FROM items ORDER BY id"
                ).fetchall()
                self.assertEqual(rows[0]["last_notified_slot"], "2026-05-25-08")
                self.assertIsNone(rows[1]["last_notified_slot"])
            finally:
                conn.close()

    def test_manager_logs_plugin_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "brief.sqlite")
            try:
                paths = Paths(
                    root=Path(tmp),
                    config=Path(tmp) / "sources.yml",
                    plugins=Path(tmp) / "plugins.yml",
                    data_dir=Path(tmp),
                    db=Path(tmp) / "brief.sqlite",
                    archive_dir=Path(tmp) / "archive",
                    log_dir=Path(tmp) / "logs",
                )
                ctx = PluginContext(conn, paths, {}, date(2026, 5, 25), {}, {})
                manager = PluginManager({"dummy": {"enabled": True}})
                manager.register(DummyPlugin())

                manager.run_stage("collector", ctx)

                health = db.load_plugin_health(conn)
                self.assertEqual(health[0]["plugin_name"], "dummy")
                self.assertEqual(health[0]["last_status"], "success")
            finally:
                conn.close()

    def test_builtin_registry_includes_enricher_plugins(self):
        registry = builtin_registry()
        settings = load_plugin_settings(Path("missing.yml"))
        rows = registry.list_plugins(settings)
        kinds = {row["name"]: row["kind"] for row in rows}

        self.assertEqual(kinds["feedback"], "enricher")
        self.assertEqual(kinds["deadline"], "enricher")
        self.assertEqual(kinds["cross_source_dedupe"], "enricher")

    def test_deadline_enricher_writes_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = db.connect(root / "brief.sqlite")
            try:
                paths = Paths(
                    root=root,
                    config=root / "sources.yml",
                    plugins=root / "plugins.yml",
                    data_dir=root,
                    db=root / "brief.sqlite",
                    archive_dir=root / "archive",
                    log_dir=root / "logs",
                )
                ctx = PluginContext(
                    conn,
                    paths,
                    {},
                    date(2026, 5, 25),
                    {},
                    {
                        "web_items": [
                            {
                                "_item_id": 1,
                                "title": "选课确认截止 2026年6月5日",
                                "content_snippet": "",
                                "url": "https://example.com/deadline",
                            }
                        ]
                    },
                )

                result = DeadlineEnricherPlugin().run(ctx)

                self.assertEqual(result.item_count, 1)
                self.assertEqual(ctx.state["deadline_events"][0]["deadline"], "2026-06-05")
                rows = db.load_deadline_events(conn)
                self.assertEqual(rows[0]["event_type"], "确认")
            finally:
                conn.close()

    def test_local_loader_registers_local_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "plugins" / "local"
            local.mkdir(parents=True)
            (local / "demo.py").write_text(
                """
from app.plugins.base import BasePlugin

class DemoPlugin(BasePlugin):
    name = "demo_local"
    kind = "collector"

def register(registry):
    registry.register(DemoPlugin)
""".strip(),
                encoding="utf-8",
            )
            registry = PluginRegistry()

            load_local_plugins(registry, root)

            self.assertIn("demo_local", registry.plugin_types)
            self.assertEqual(registry.load_errors, [])


if __name__ == "__main__":
    unittest.main()
