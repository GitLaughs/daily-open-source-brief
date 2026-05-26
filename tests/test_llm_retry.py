from __future__ import annotations

import unittest
from unittest.mock import patch

from app.llm_retry import is_transient, retry_on_transient


class LlmRetryTests(unittest.TestCase):
    def test_transient_markers(self):
        self.assertTrue(is_transient("HTTP 429 rate limit"))
        self.assertTrue(is_transient("connection timeout"))
        self.assertFalse(is_transient("HTTP 401 unauthorized"))

    def test_retry_then_success(self):
        calls = {"count": 0}

        @retry_on_transient(max_retries=2, base_delay=0)
        def flaky() -> str:
            calls["count"] += 1
            if calls["count"] < 2:
                raise RuntimeError("HTTP 503")
            return "ok"

        with patch("app.llm_retry.time.sleep"):
            self.assertEqual(flaky(), "ok")
        self.assertEqual(calls["count"], 2)

    def test_permanent_error_not_retried(self):
        calls = {"count": 0}

        @retry_on_transient(max_retries=2, base_delay=0)
        def bad() -> str:
            calls["count"] += 1
            raise RuntimeError("HTTP 401")

        with self.assertRaises(RuntimeError):
            bad()
        self.assertEqual(calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
