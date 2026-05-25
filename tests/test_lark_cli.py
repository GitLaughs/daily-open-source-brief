from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from app import lark_cli


class LarkCliTests(unittest.TestCase):
    def test_run_lark_json_parses_payload(self):
        completed = subprocess.CompletedProcess(
            ["lark-cli"],
            0,
            stdout='{"ok": true, "data": {"message_id": "om_1"}}',
            stderr="",
        )
        with patch("app.lark_cli.subprocess.run", return_value=completed) as run:
            payload = lark_cli.run_lark_json(["im", "+messages-send"])
        self.assertEqual(payload["data"]["message_id"], "om_1")
        run.assert_called_once()

    def test_run_lark_raises_on_nonzero_exit(self):
        completed = subprocess.CompletedProcess(["lark-cli"], 1, stdout="", stderr="permission denied")
        with patch("app.lark_cli.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                lark_cli.run_lark(["im"])


if __name__ == "__main__":
    unittest.main()
