from __future__ import annotations

import unittest
from unittest.mock import patch

from app import lark_sender


class LarkSenderTests(unittest.TestCase):
    def test_split_markdown_keeps_short_message_single_part(self):
        parts = lark_sender.split_markdown("## 标题\n\n正文", max_chars=100)
        self.assertEqual(parts, ["## 标题\n\n正文\n"])

    def test_split_markdown_splits_by_blocks(self):
        markdown = "## 标题\n\n" + "\n\n".join([f"- item {i}" for i in range(10)])
        parts = lark_sender.split_markdown(markdown, max_chars=30)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 31 for part in parts))

    def test_send_lark_message_uses_part_idempotency_keys(self):
        calls: list[list[str]] = []

        def fake_run(args, timeout=60):
            calls.append(list(args))
            return {"ok": True, "data": {"message_id": f"om_{len(calls)}"}}

        env = {
            "LARK_AS": "bot",
            "LARK_USER_ID": "ou_demo",
            "LARK_MAX_MARKDOWN_CHARS": "20",
        }
        with patch.dict("app.lark_sender.os.environ", env, clear=True):
            with patch("app.lark_sender.run_lark_json", side_effect=fake_run):
                data = lark_sender.send_lark_message("## 标题\n\n" + ("正文" * 20), "2026-05-25-08")

        self.assertGreater(data["parts"], 1)
        self.assertEqual(len(data["message_ids"]), data["parts"])
        self.assertIn("daily-open-source-brief-2026-05-25-08-1", calls[0])
        self.assertIn("--user-id", calls[0])
        self.assertIn("ou_demo", calls[0])


if __name__ == "__main__":
    unittest.main()
