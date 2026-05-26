from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import requests

from .llm_retry import retry_on_transient


SYSTEM_PROMPT = """你是我的个性日报助理。
输入包含 GitHub 仓库、校园官网公开通知、RSS/通用新闻和半导体/EDA 产业资讯。
请筛掉低价值重复内容，输出一份中文日报：
1. 今日优先处理
2. 校园与产业资讯雷达
3. 今日最值得看的开源项目
4. 可后续尝试的项目
每条不超过 120 字，保留链接。
"""


def compact_repo(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": repo.get("full_name"),
        "url": repo.get("html_url"),
        "description": repo.get("description"),
        "stars": repo.get("stargazers_count"),
        "language": repo.get("language"),
        "license": (repo.get("license") or {}).get("spdx_id") if isinstance(repo.get("license"), dict) else None,
        "topics": repo.get("topics") or [],
        "pushed_at": repo.get("pushed_at"),
        "score": repo.get("_effective_score", repo.get("_score")),
    }


def compact_web_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": item.get("source_title") or item.get("source_name"),
        "category": item.get("category"),
        "title": item.get("title"),
        "url": item.get("url"),
        "published_at": item.get("published_at"),
        "snippet": item.get("content_snippet"),
        "score": item.get("_effective_score", item.get("_score")),
    }


def load_preference_context() -> str:
    path = Path(os.getenv("DAILY_BRIEF_PROFILE", "config/profile.yml"))
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:3000]


def llm_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL"))


def summarize_with_llm(
    repos: list[dict[str, Any]],
    web_items: Optional[list[dict[str, Any]]] = None,
    source_errors: Optional[list[dict[str, str]]] = None,
    timeout: int = 60,
) -> Optional[str]:
    if not llm_configured():
        return None
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ["OPENAI_MODEL"]
    user_content = json.dumps(
        {
            "profile_preferences": load_preference_context(),
            "repositories": [compact_repo(r) for r in repos[:40]],
            "web_and_rss_items": [compact_web_item(item) for item in (web_items or [])[:60]],
            "source_errors": source_errors or [],
        },
        ensure_ascii=False,
    )
    reasoning_effort = os.getenv("DAILY_BRIEF_REASONING_EFFORT", "").strip()
    responses_payload: dict[str, Any] = {
        "model": model,
        "instructions": SYSTEM_PROMPT,
        "input": user_content,
        "temperature": 0.3,
        "max_output_tokens": 3000,
    }
    if reasoning_effort:
        responses_payload["reasoning"] = {"effort": reasoning_effort}
    response = post_responses_api(base_url, responses_payload, timeout)
    if response.status_code < 400:
        return extract_responses_text(parse_json_response(response)).strip()

    response = post_chat_completion(base_url, model, user_content, timeout)
    return extract_chat_text(parse_json_response(response)).strip()


@retry_on_transient()
def post_responses_api(base_url: str, payload: dict[str, Any], timeout: int) -> requests.Response:
    try:
        response = requests.post(f"{base_url}/responses", headers=llm_headers(), json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"LLM Responses API request failed: {exc}") from exc
    if response.status_code >= 400 and response.status_code not in {400, 404, 405, 422}:
        raise RuntimeError(f"LLM Responses API error {response.status_code}: {response.text[:300]}")
    return response


@retry_on_transient()
def post_chat_completion(base_url: str, model: str, user_content: str, timeout: int) -> requests.Response:
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=llm_headers(),
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.3,
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"LLM Chat API request failed: {exc}") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"LLM Chat API error {response.status_code}: {response.text[:300]}")
    return response


def llm_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }


def parse_json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"LLM API returned non-JSON response: {response.text[:300]!r}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("LLM API returned non-object JSON")
    return payload


def extract_responses_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    raise RuntimeError("LLM Responses API returned no text")


def extract_chat_text(payload: dict[str, Any]) -> str:
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM Chat API returned no message content") from exc
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("LLM Chat API returned empty message content")
    return text


def fallback_digest(
    repos: list[dict[str, Any]],
    web_items: Optional[list[dict[str, Any]]] = None,
    source_errors: Optional[list[dict[str, str]]] = None,
    deadline_events: Optional[list[dict[str, Any]]] = None,
) -> str:
    web_items = web_items or []
    deadline_events = deadline_events or []
    if not repos and not web_items and not deadline_events:
        return "今日无高价值 GitHub 仓库、校园官网或 RSS 资讯更新。"

    lines = ["# 今日个人日报"]
    active_deadlines = [event for event in deadline_events if event.get("status") != "expired"]
    if active_deadlines:
        lines.extend(["", "## 今日优先处理"])
        for event in active_deadlines[:5]:
            lines.append(
                f"- [{event.get('event_type', '事项')}] {event.get('title', '未命名')}："
                f"{event.get('deadline')} 截止\n  链接：{event.get('source_url') or ''}"
            )
    if web_items:
        if not active_deadlines:
            lines.extend(["", "## 今日优先处理"])
        else:
            lines.extend(["", "## 校园与产业资讯雷达"])
        for item in web_items[:5]:
            lines.append(format_web_item(item))
        if len(web_items) > 5:
            lines.extend(["", "## 校园与产业资讯雷达"])
            for item in web_items[5:12]:
                lines.append(format_web_item(item))

    if repos:
        lines.extend(["", "## 今日最值得看"])
    for repo in repos[:5]:
        lines.append(format_repo(repo))
    if len(repos) > 5:
        lines.extend(["", "## GitHub 高星项目观察"])
        for repo in repos[5:15]:
            lines.append(format_repo(repo))
    if len(repos) > 15:
        lines.extend(["", "## 可后续尝试的项目"])
        for repo in repos[15:20]:
            lines.append(format_repo(repo))
    if source_errors:
        lines.extend(["", "## 来源状态"])
        for error in source_errors[:5]:
            lines.append(f"- {error.get('source_name', 'source')} 抓取失败：{error.get('error', 'unknown')}")
    return "\n".join(lines)


def format_repo(repo: dict[str, Any]) -> str:
    license_obj = repo.get("license") or {}
    license_name = license_obj.get("spdx_id") if isinstance(license_obj, dict) else ""
    topics = ", ".join((repo.get("topics") or [])[:4])
    return (
        f"- {repo['full_name']} / {repo.get('stargazers_count', 0)} stars / "
        f"{repo.get('language') or 'Unknown'} / {license_name or 'Unknown'}\n"
        f"  {repo.get('description') or '暂无简介'}\n"
        f"  值得看：评分 {repo.get('_effective_score', repo.get('_score', 0))}，主题 {topics or '未标注'}，最近更新 {repo.get('pushed_at') or '未知'}。\n"
        f"  链接：{repo['html_url']}"
    )


def format_web_item(item: dict[str, Any]) -> str:
    source = item.get("source_title") or item.get("source_name") or "官网"
    published_at = item.get("published_at") or "日期未知"
    snippet = item.get("content_snippet") or ""
    if snippet:
        snippet = f"\n  摘要：{snippet}"
    return (
        f"- [{source}] {item.get('title', '未命名')}（{published_at}）"
        f"{snippet}\n"
        f"  链接：{item.get('url')}"
    )


def build_digest(
    repos: list[dict[str, Any]],
    web_items: Optional[list[dict[str, Any]]] = None,
    source_errors: Optional[list[dict[str, str]]] = None,
    deadline_events: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, str]:
    try:
        llm_text = summarize_with_llm(repos, web_items=web_items, source_errors=source_errors)
    except Exception as exc:
        if os.getenv("LLM_FALLBACK_ON_ERROR", "").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from .ccswitch import configure_from_ccswitch

                provider = configure_from_ccswitch(force_fallback=True)
                llm_text = summarize_with_llm(repos, web_items=web_items, source_errors=source_errors)
                if llm_text:
                    name = provider["name"] if provider else "fallback"
                    return llm_text, f"llm_fallback:{name}"
            except Exception as fallback_exc:
                return fallback_digest(repos, web_items, source_errors, deadline_events), f"llm_failed: {exc}; fallback_failed: {fallback_exc}"
        return fallback_digest(repos, web_items, source_errors, deadline_events), f"llm_failed: {exc}"
    if llm_text:
        return llm_text, "llm"
    return fallback_digest(repos, web_items, source_errors, deadline_events), "template"
