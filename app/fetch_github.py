from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import requests

from .config import env_bool


GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


def github_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token and not env_bool("DAILY_BRIEF_ALLOW_UNAUTHENTICATED_GITHUB"):
        raise RuntimeError("Missing GITHUB_TOKEN. Set DAILY_BRIEF_ALLOW_UNAUTHENTICATED_GITHUB=1 only for limited manual trials.")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "daily-open-source-brief",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def search_repositories(query: str, limit: int, timeout: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    headers = github_headers()
    page = 1
    while len(items) < limit:
        per_page = min(100, limit - len(items))
        response = requests.get(
            GITHUB_SEARCH_URL,
            headers=headers,
            params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page, "page": page},
            timeout=timeout,
        )
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RuntimeError("GitHub API rate limit reached")
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API error {response.status_code}: {response.text[:300]}")
        payload = response.json()
        batch = payload.get("items", [])
        if not batch:
            break
        items.extend(batch)
        page += 1
    return items


def fetch_from_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    repos_by_name: dict[str, dict[str, Any]] = {}
    for query in config.get("github", {}).get("queries", []):
        name = query.get("name", "github-search")
        q = query["q"]
        limit = int(query.get("limit", 20))
        for repo in search_repositories(q, limit):
            repo["_source_query"] = name
            repos_by_name[repo["full_name"].lower()] = repo
    return list(repos_by_name.values())


def repo_to_item(repo: dict[str, Any], source_id: int, score: float) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    full_name = repo["full_name"]
    return {
        "source_id": source_id,
        "source_type": "github_repo",
        "title": full_name,
        "url": repo["html_url"],
        "content_snippet": repo.get("description") or "",
        "raw_json": json.dumps(repo, ensure_ascii=False),
        "hash": full_name.lower(),
        "published_at": repo.get("created_at"),
        "fetched_at": now,
        "score": score,
        "status": "new",
    }


def sample_repositories() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return [
        {
            "full_name": "astral-sh/uv",
            "html_url": "https://github.com/astral-sh/uv",
            "description": "An extremely fast Python package and project manager, written in Rust.",
            "stargazers_count": 61000,
            "forks_count": 1700,
            "open_issues_count": 600,
            "language": "Rust",
            "license": {"spdx_id": "MIT"},
            "topics": ["python", "packaging", "developer-tools", "rust"],
            "pushed_at": now,
            "created_at": "2024-02-15T00:00:00Z",
        },
        {
            "full_name": "ollama/ollama",
            "html_url": "https://github.com/ollama/ollama",
            "description": "Get up and running with large language models.",
            "stargazers_count": 148000,
            "forks_count": 12000,
            "open_issues_count": 1200,
            "language": "Go",
            "license": {"spdx_id": "MIT"},
            "topics": ["ai", "llm", "self-hosted"],
            "pushed_at": now,
            "created_at": "2023-06-26T00:00:00Z",
        },
        {
            "full_name": "actualbudget/actual",
            "html_url": "https://github.com/actualbudget/actual",
            "description": "A local-first personal finance app.",
            "stargazers_count": 21000,
            "forks_count": 1700,
            "open_issues_count": 900,
            "language": "TypeScript",
            "license": {"spdx_id": "MIT"},
            "topics": ["self-hosted", "finance", "local-first"],
            "pushed_at": now,
            "created_at": "2019-09-01T00:00:00Z",
        },
    ]

