from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from .fetch_webpage import DEFAULT_USER_AGENT, normalize_space


def fetch_trending(language: str = "any", since: str = "daily", timeout: int = 15) -> list[dict[str, Any]]:
    path = "" if language in {"", "any", "all"} else f"/{language}"
    url = f"https://github.com/trending{path}?since={since}"
    response = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html"}, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}")
    return parse_trending(response.text, language=language, since=since)


def parse_trending(text: str, *, language: str = "any", since: str = "daily") -> list[dict[str, Any]]:
    soup = BeautifulSoup(text, "html.parser")
    repos: list[dict[str, Any]] = []
    for article in soup.select("article.Box-row"):
        heading = article.select_one("h2 a")
        if not heading:
            continue
        repo_path = normalize_space(heading.get_text(" "))
        full_name = re.sub(r"\s*/\s*", "/", repo_path).strip()
        if "/" not in full_name:
            continue
        description_node = article.select_one("p")
        stars_link = article.select_one('a[href$="/stargazers"]')
        stars_today_node = article.find(string=re.compile(r"stars today", re.I))
        repo_language_node = article.select_one("[itemprop='programmingLanguage']")
        repos.append(
            {
                "full_name": full_name,
                "html_url": f"https://github.com/{full_name}",
                "description": normalize_space(description_node.get_text(" ")) if description_node else "",
                "stargazers_count": parse_int(stars_link.get_text(" ") if stars_link else "0"),
                "stars_today": parse_int(str(stars_today_node or "0")),
                "language": normalize_space(repo_language_node.get_text(" ")) if repo_language_node else None,
                "trending_language": language,
                "trending_since": since,
                "topics": ["github-trending"],
            }
        )
    return repos


def parse_int(text: str) -> int:
    match = re.search(r"[\d,]+", text)
    return int(match.group(0).replace(",", "")) if match else 0
