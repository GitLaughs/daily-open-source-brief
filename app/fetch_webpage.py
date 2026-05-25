from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; daily-open-source-brief/0.2; "
    "+https://github.com/daily-open-source-brief)"
)

DATE_PATTERNS = [
    re.compile(r"(?P<y>20\d{2})[-/.年](?P<m>\d{1,2})[-/.月](?P<d>\d{1,2})"),
    re.compile(r"(?P<d>\d{1,2})\s+(?P<y>20\d{2})[-/.](?P<m>\d{1,2})"),
]

SKIP_TITLES = {
    "首页",
    "上一页",
    "下一页",
    "尾页",
    "末页",
    "更多",
    "more",
    "返回首页",
}


@dataclass(frozen=True)
class FetchError:
    source_name: str
    url: str
    error: str

    def as_dict(self) -> dict[str, str]:
        return {"source_name": self.source_name, "url": self.url, "error": self.error}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_webpages_from_config(
    config: dict[str, Any],
    *,
    today: Optional[date] = None,
    timeout: int = 25,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    today = today or date.today()
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    runs: list[dict[str, Any]] = []
    global_keywords = list(config.get("school", {}).get("priority_keywords") or [])
    for source in config.get("webpages", []) or []:
        if not source.get("enabled", True):
            continue
        source_config = dict(source)
        source_config["priority_keywords"] = global_keywords + list(source.get("priority_keywords") or [])
        started_at = utc_now()
        started = time.perf_counter()
        try:
            source_entries = fetch_webpage_source(source_config, today=today, timeout=timeout)
            entries.extend(source_entries)
            runs.append(
                source_run(
                    source_config,
                    "success",
                    item_count=len(source_entries),
                    started_at=started_at,
                    duration_ms=elapsed_ms(started),
                )
            )
        except Exception as exc:
            errors.append(FetchError(str(source.get("name") or source.get("url") or "webpage"), str(source.get("url") or ""), str(exc)).as_dict())
            runs.append(
                source_run(
                    source_config,
                    "failed",
                    error_message=str(exc),
                    started_at=started_at,
                    duration_ms=elapsed_ms(started),
                )
            )
    return dedupe_entries(entries), errors, runs


def elapsed_ms(started: float) -> int:
    return max(int((time.perf_counter() - started) * 1000), 0)


def source_run(
    source: dict[str, Any],
    status: str,
    *,
    item_count: int = 0,
    error_message: Optional[str] = None,
    started_at: str,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "source_name": str(source.get("name") or source.get("url") or "webpage"),
        "source_type": str(source.get("source_type") or "school_notice"),
        "url": source.get("url"),
        "status": status,
        "item_count": item_count,
        "duration_ms": duration_ms,
        "error_message": error_message,
        "started_at": started_at,
        "finished_at": utc_now(),
    }


def fetch_webpage_source(source: dict[str, Any], *, today: date, timeout: int = 25) -> list[dict[str, Any]]:
    url = str(source["url"])
    session = requests.Session()
    text = fetch_html(session, url, timeout=timeout)
    entries = parse_webpage_entries(text, url, source, today=today)
    limit = int(source.get("limit", 12))
    return entries[:limit]


def fetch_html(session: requests.Session, url: str, *, timeout: int = 25) -> str:
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    response = session.get(url, headers=headers, timeout=timeout)
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}")
    text = response.text
    if is_dynamic_challenge(text):
        solve_dynamic_challenge_with_retry(session, url, text, headers=headers, timeout=timeout)
        response = session.get(url, headers=headers, timeout=timeout)
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} after challenge")
        text = response.text
        if is_dynamic_challenge(text):
            raise RuntimeError("dynamic challenge not solved")
    return text


def is_dynamic_challenge(text: str) -> bool:
    return "dynamic_challenge" in text and "challengeId" in text and "answer" in text


def solve_dynamic_challenge_with_retry(
    session: requests.Session,
    page_url: str,
    text: str,
    *,
    headers: dict[str, str],
    timeout: int,
) -> None:
    last_error: Optional[Exception] = None
    current_text = text
    for attempt in range(2):
        try:
            solve_dynamic_challenge(session, page_url, current_text, headers=headers, timeout=timeout)
            return
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                response = session.get(
                    page_url,
                    headers={**headers, "Cache-Control": "no-cache", "Pragma": "no-cache"},
                    timeout=timeout,
                )
                response.encoding = response.apparent_encoding or response.encoding or "utf-8"
                current_text = response.text
                continue
    raise RuntimeError(str(last_error) if last_error else "dynamic challenge failed")


def solve_dynamic_challenge(
    session: requests.Session,
    page_url: str,
    text: str,
    *,
    headers: dict[str, str],
    timeout: int,
) -> None:
    challenge_id = find_first(r"challengeId\s*=\s*\"([^\"]+)\"", text)
    answer_text = find_first(r"answer\s*=\s*(\d+)", text)
    if not challenge_id or not answer_text:
        raise RuntimeError("dynamic challenge markers missing")
    parsed = urlparse(page_url)
    endpoint = f"{parsed.scheme}://{parsed.netloc}/dynamic_challenge"
    response = session.post(
        endpoint,
        headers={
            "User-Agent": headers["User-Agent"],
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": page_url,
        },
        json={
            "challenge_id": challenge_id,
            "answer": int(answer_text),
            "browser_info": {
                "userAgent": headers["User-Agent"],
                "language": "zh-CN",
                "platform": "Win32",
                "cookieEnabled": True,
                "hardwareConcurrency": 4,
                "deviceMemory": 4,
                "timezone": "Asia/Shanghai",
            },
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"dynamic challenge HTTP {response.status_code}")
    payload = response.json()
    if not payload.get("success") or not payload.get("client_id"):
        raise RuntimeError("dynamic challenge rejected")
    session.cookies.set("client_id", str(payload["client_id"]), domain=parsed.hostname, path="/")


def parse_webpage_entries(
    text: str,
    page_url: str,
    source: dict[str, Any],
    *,
    today: date,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    fetched_at = utc_now()
    source_name = str(source.get("name") or source.get("title") or page_url)
    source_title = str(source.get("title") or source_name)
    blocks = re.findall(r"<li\b[\s\S]*?</li>", text, flags=re.IGNORECASE)
    if not blocks:
        blocks = re.findall(r"<tr\b[\s\S]*?</tr>", text, flags=re.IGNORECASE)

    for block in blocks:
        anchor = first_anchor(block)
        if not anchor:
            continue
        href, attrs, inner = anchor
        url = normalize_url(page_url, href)
        title = clean_title(attrs.get("title") or strip_tags(inner))
        if not title or should_skip_title(title):
            continue
        if not url_allowed(url, source):
            continue
        published_at = extract_date(block) or extract_date(inner)
        snippet = clean_snippet(block, title)
        entry = {
            "source_name": source_name,
            "source_title": source_title,
            "source_type": source.get("source_type") or "school_notice",
            "category": source.get("category") or "campus",
            "title": title,
            "url": url,
            "published_at": published_at,
            "fetched_at": fetched_at,
            "content_snippet": snippet,
            "tags": list(source.get("tags") or []),
            "_source_config": {
                "name": source_name,
                "url": page_url,
                "title": source_title,
                "category": source.get("category") or "campus",
            },
        }
        entry["_score"] = score_web_entry(entry, source, today=today)
        candidates.append(entry)
    candidates.sort(key=lambda item: (item.get("_score", 0), item.get("published_at") or ""), reverse=True)
    return dedupe_entries(candidates)


def first_anchor(block: str) -> Optional[tuple[str, dict[str, str], str]]:
    match = re.search(r"<a\b(?P<attrs>[^>]*)>(?P<inner>[\s\S]*?)</a>", block, flags=re.IGNORECASE)
    if not match:
        return None
    attrs = parse_attrs(match.group("attrs"))
    href = attrs.get("href")
    if not href:
        return None
    return href, attrs, match.group("inner")


def parse_attrs(attr_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _quote, value in re.findall(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(['\"])(.*?)\2", attr_text, flags=re.DOTALL):
        attrs[key.lower()] = html.unescape(value)
    return attrs


def normalize_url(page_url: str, href: str) -> str:
    href = html.unescape(href.strip())
    return urljoin(page_url, href)


def url_allowed(url: str, source: dict[str, Any]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    allowed_domains = list(source.get("allowed_domains") or [])
    if allowed_domains and parsed.netloc not in allowed_domains:
        return False
    allow_patterns = [str(item) for item in source.get("url_allow_patterns") or []]
    if allow_patterns and not any(pattern in url for pattern in allow_patterns):
        return False
    return True


def should_skip_title(title: str) -> bool:
    normalized = title.strip().lower()
    return normalized in SKIP_TITLES or len(normalized) < 4


def clean_title(value: str) -> str:
    value = normalize_space(value)
    for pattern in DATE_PATTERNS:
        value = pattern.sub("", value, count=1).strip()
    value = re.sub(r"^\d{1,2}\s+", "", value).strip()
    return value[:180]


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[\s\S]*?</script>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<style\b[\s\S]*?</style>", " ", value, flags=re.IGNORECASE)
    return html.unescape(re.sub(r"<[^>]+>", " ", value))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def clean_snippet(block: str, title: str) -> str:
    plain = normalize_space(strip_tags(block))
    for pattern in DATE_PATTERNS:
        plain = pattern.sub("", plain, count=1).strip()
    plain = plain.replace(title, "", 1).strip(" -:：")
    if not plain:
        return ""
    return plain[:220]


def extract_date(value: str) -> Optional[str]:
    plain = normalize_space(strip_tags(value))
    for pattern in DATE_PATTERNS:
        match = pattern.search(plain)
        if not match:
            continue
        try:
            y = int(match.group("y"))
            m = int(match.group("m"))
            d = int(match.group("d"))
            return date(y, m, d).isoformat()
        except ValueError:
            continue
    return None


def score_web_entry(entry: dict[str, Any], source: dict[str, Any], *, today: date) -> float:
    score = 45.0 + float(source.get("weight", 0) or 0)
    published = parse_date(entry.get("published_at"))
    if published:
        age_days = max((today - published).days, 0)
        if age_days <= 3:
            score += 30
        elif age_days <= 14:
            score += 22
        elif age_days <= 45:
            score += 12
        elif age_days > 180:
            score -= 18

    text = f"{entry.get('title', '')} {entry.get('content_snippet', '')}"
    priority_keywords = list(source.get("priority_keywords") or [])
    action_keywords = [
        "报名",
        "申报",
        "选课",
        "考试",
        "培养",
        "毕业",
        "确认",
        "办理",
        "公示",
        "竞赛",
        "讲座",
        "答辩",
        "奖学金",
        "助学",
        "网络",
        "账号",
        "统一身份认证",
    ]
    for keyword in priority_keywords:
        if str(keyword) and str(keyword) in text:
            score += 14
    for keyword in action_keywords:
        if keyword in text:
            score += 8
    return round(score, 2)


def parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def dedupe_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for entry in entries:
        key = str(entry.get("url") or entry.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def web_entry_to_item(entry: dict[str, Any], source_id: int) -> dict[str, Any]:
    raw = {key: value for key, value in entry.items() if key != "_source_config"}
    return {
        "source_id": source_id,
        "source_type": str(entry.get("source_type") or "school_notice"),
        "title": str(entry["title"]),
        "url": str(entry["url"]),
        "content_snippet": str(entry.get("content_snippet") or ""),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "hash": str(entry["url"]).lower(),
        "published_at": entry.get("published_at"),
        "fetched_at": entry.get("fetched_at") or utc_now(),
        "score": float(entry.get("_score") or 0),
        "status": "new",
    }


def find_first(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None
