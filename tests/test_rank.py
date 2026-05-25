from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.rank import score_repo


class RankTests(unittest.TestCase):
    def test_score_prefers_topic_language_and_recent_push(self):
        config = {
            "topics": {"include": ["ai", "self-hosted"]},
            "languages": {"include": ["Go"]},
        }
        repo = {
            "stargazers_count": 10000,
            "topics": ["ai", "self-hosted"],
            "language": "Go",
            "license": {"spdx_id": "MIT"},
            "pushed_at": "2026-05-24T00:00:00Z",
        }
        score = score_repo(repo, config, now=datetime(2026, 5, 25, tzinfo=timezone.utc))
        self.assertGreater(score, 130)

    def test_archived_repo_is_penalized(self):
        config = {"topics": {"include": []}, "languages": {"include": []}}
        repo = {
            "stargazers_count": 100000,
            "archived": True,
            "pushed_at": "2026-05-24T00:00:00Z",
        }
        self.assertLess(score_repo(repo, config, now=datetime(2026, 5, 25, tzinfo=timezone.utc)), 30)


if __name__ == "__main__":
    unittest.main()
