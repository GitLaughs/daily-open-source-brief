from __future__ import annotations

import unittest
from unittest.mock import patch

from app.http_client import http_session, trust_env_proxy


class HttpClientTests(unittest.TestCase):
    def test_http_session_ignores_system_proxy_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            session = http_session()
            try:
                self.assertFalse(session.trust_env)
            finally:
                session.close()

    def test_http_session_can_opt_into_environment_proxy(self):
        with patch.dict("os.environ", {"DAILY_BRIEF_TRUST_ENV_PROXY": "1"}, clear=True):
            self.assertTrue(trust_env_proxy())
            session = http_session()
            try:
                self.assertTrue(session.trust_env)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
