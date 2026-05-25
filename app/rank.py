from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def score_repo(repo: dict[str, Any], config: dict[str, Any], now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)
    stars = int(repo.get("stargazers_count") or 0)
    score = math.log10(max(stars, 1)) * 20

    pushed_at = parse_dt(repo.get("pushed_at"))
    if pushed_at:
        age_days = max((now - pushed_at).days, 0)
        if age_days <= 7:
            score += 25
        elif age_days <= 30:
            score += 18
        elif age_days <= 90:
            score += 10
        elif age_days > 180:
            score -= 25

    topics = {str(t).lower() for t in repo.get("topics") or []}
    include_topics = {str(t).lower() for t in config.get("topics", {}).get("include", [])}
    score += len(topics & include_topics) * 12

    language = repo.get("language")
    include_languages = set(config.get("languages", {}).get("include", []))
    if language in include_languages:
        score += 8

    license_obj = repo.get("license") or {}
    if isinstance(license_obj, dict) and license_obj.get("spdx_id") not in {None, "NOASSERTION"}:
        score += 5

    if repo.get("archived") or repo.get("fork"):
        score -= 100

    return round(score, 2)


def top_repos(repos: list[dict[str, Any]], config: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    for repo in repos:
        repo["_score"] = score_repo(repo, config)
    return sorted(repos, key=lambda r: (r.get("_score", 0), r.get("stargazers_count", 0)), reverse=True)[:limit]
