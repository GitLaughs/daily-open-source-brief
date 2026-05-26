from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Optional

import requests

from .fetch_webpage import DEFAULT_USER_AGENT, dedupe_entries, normalize_space, strip_tags


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_rss_from_config(
    config: dict[str, Any],
    *,
    today: Optional[date] = None,
    timeout: int = 18,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    today = today or date.today()
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    runs: list[dict[str, Any]] = []
    global_keywords = list(config.get("industry", {}).get("priority_keywords") or [])
    sources = [source for source in config.get("rss", []) or [] if source.get("enabled", True)]

    def collect_one(source: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
        source_config = dict(source)
        source_config["priority_keywords"] = global_keywords + list(source.get("priority_keywords") or [])
        started_at = utc_now()
        started = time.perf_counter()
        try:
            source_entries = fetch_rss_source(source_config, today=today, timeout=timeout)
            return source_entries, [], source_run(source_config, "success", len(source_entries), None, started_at, elapsed_ms(started))
        except Exception as exc:
            error = {"source_name": str(source.get("name") or source.get("url") or "rss"), "url": str(source.get("url") or ""), "error": str(exc)}
            return [], [error], source_run(source_config, "failed", 0, str(exc), started_at, elapsed_ms(started))

    if not sources:
        return [], [], []
    workers = min(len(sources), int(config.get("rss_parallel_workers") or 4))
    if workers <= 1:
        results = [collect_one(source) for source in sources]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(collect_one, source): index for index, source in enumerate(sources)}
            ordered: list[tuple[int, tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]]] = []
            for future in as_completed(futures):
                ordered.append((futures[future], future.result()))
            results = [result for _index, result in sorted(ordered, key=lambda item: item[0])]
    for source_entries, source_errors, source_run_item in results:
        entries.extend(source_entries)
        errors.extend(source_errors)
        runs.append(source_run_item)
    return dedupe_entries(entries), errors, runs


def fetch_rss_source(source: dict[str, Any], *, today: date, timeout: int = 18) -> list[dict[str, Any]]:
    url = str(source["url"])
    response = requests.get(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}")
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    entries = parse_rss_entries(response.text, source, today=today)
    return entries[: int(source.get("limit", 12))]


def parse_rss_entries(xml_text: str, source: dict[str, Any], *, today: date) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        raise RuntimeError(f"RSS parse failed: {exc}") from exc
    fetched_at = utc_now()
    source_name = str(source.get("name") or source.get("url") or "rss")
    source_title = str(source.get("title") or source_name)
    entries: list[dict[str, Any]] = []

    if local_name(root.tag) == "rss":
        items = root.findall(".//item")
        for item in items:
            entry = entry_from_rss_item(item, source, source_name, source_title, fetched_at, today)
            if entry:
                entries.append(entry)
    elif local_name(root.tag) == "feed":
        for item in root:
            if local_name(item.tag) != "entry":
                continue
            entry = entry_from_atom_item(item, source, source_name, source_title, fetched_at, today)
            if entry:
                entries.append(entry)
    else:
        raise RuntimeError(f"Unsupported feed root: {local_name(root.tag)}")

    entries.sort(key=lambda item: (item.get("_score", 0), item.get("published_at") or ""), reverse=True)
    return dedupe_entries(entries)


def entry_from_rss_item(
    item: ET.Element,
    source: dict[str, Any],
    source_name: str,
    source_title: str,
    fetched_at: str,
    today: date,
) -> Optional[dict[str, Any]]:
    title = clean_text(child_text(item, "title"))
    url = clean_text(child_text(item, "link"))
    if not title or not url:
        return None
    published_at = parse_feed_date(child_text(item, "pubDate") or child_text(item, "published") or child_text(item, "updated"))
    description = clean_text(child_text(item, "description") or child_text(item, "summary") or child_text(item, "encoded"))
    guid = clean_text(child_text(item, "guid")) or url
    return make_entry(source, source_name, source_title, title, url, description, published_at, fetched_at, guid, today)


def entry_from_atom_item(
    item: ET.Element,
    source: dict[str, Any],
    source_name: str,
    source_title: str,
    fetched_at: str,
    today: date,
) -> Optional[dict[str, Any]]:
    title = clean_text(child_text(item, "title"))
    url = atom_link(item)
    if not title or not url:
        return None
    published_at = parse_feed_date(child_text(item, "published") or child_text(item, "updated"))
    description = clean_text(child_text(item, "summary") or child_text(item, "content"))
    guid = clean_text(child_text(item, "id")) or url
    return make_entry(source, source_name, source_title, title, url, description, published_at, fetched_at, guid, today)


def make_entry(
    source: dict[str, Any],
    source_name: str,
    source_title: str,
    title: str,
    url: str,
    description: str,
    published_at: Optional[str],
    fetched_at: str,
    guid: str,
    today: date,
) -> dict[str, Any]:
    entry = {
        "source_name": source_name,
        "source_title": source_title,
        "source_type": source.get("source_type") or "rss_entry",
        "category": source.get("category") or "rss",
        "title": title[:220],
        "url": url,
        "published_at": published_at,
        "fetched_at": fetched_at,
        "content_snippet": description[:260],
        "guid": guid,
        "tags": list(source.get("tags") or []),
        "_source_config": {
            "name": source_name,
            "url": source.get("url"),
            "title": source_title,
            "category": source.get("category") or "rss",
        },
    }
    entry["_score"] = score_rss_entry(entry, source, today=today)
    return entry


def score_rss_entry(entry: dict[str, Any], source: dict[str, Any], *, today: date) -> float:
    score = 38.0 + float(source.get("weight", 0) or 0)
    published = parse_date(entry.get("published_at"))
    if published:
        age_days = max((today - published).days, 0)
        if age_days <= 2:
            score += 28
        elif age_days <= 7:
            score += 20
        elif age_days <= 30:
            score += 10
        elif age_days > 180:
            score -= 18
    text = f"{entry.get('title', '')} {entry.get('content_snippet', '')}".lower()
    default_keywords = [
        "semiconductor",
        "chip",
        "eda",
        "analog",
        "fpga",
        "ai",
        "accelerator",
        "verification",
        "packaging",
        "foundry",
        "open source",
        "python",
    ]
    for keyword in default_keywords + [str(item).lower() for item in source.get("priority_keywords") or []]:
        if keyword and keyword in text:
            score += 8
    return round(score, 2)


def rss_entry_to_item(entry: dict[str, Any], source_id: int) -> dict[str, Any]:
    raw = {key: value for key, value in entry.items() if key != "_source_config"}
    return {
        "source_id": source_id,
        "source_type": str(entry.get("source_type") or "rss_entry"),
        "title": str(entry["title"]),
        "url": str(entry["url"]),
        "content_snippet": str(entry.get("content_snippet") or ""),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "hash": str(entry.get("guid") or entry["url"]).lower(),
        "published_at": entry.get("published_at"),
        "fetched_at": entry.get("fetched_at") or utc_now(),
        "score": float(entry.get("_score") or 0),
        "status": "new",
    }


def parse_feed_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    for candidate in (text[:10], text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date().isoformat()
        except ValueError:
            continue
    return None


def parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def child_text(item: ET.Element, name: str) -> str:
    for child in item:
        if local_name(child.tag) == name:
            return child.text or ""
    return ""


def atom_link(item: ET.Element) -> str:
    fallback = ""
    for child in item:
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "")
        rel = child.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if href and not fallback:
            fallback = href
    return fallback


def clean_text(value: str) -> str:
    return normalize_space(strip_tags(value))


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def elapsed_ms(started: float) -> int:
    return max(int((time.perf_counter() - started) * 1000), 0)


def source_run(
    source: dict[str, Any],
    status: str,
    item_count: int,
    error_message: Optional[str],
    started_at: str,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "source_name": str(source.get("name") or source.get("url") or "rss"),
        "source_type": str(source.get("source_type") or "rss_entry"),
        "url": source.get("url"),
        "status": status,
        "item_count": item_count,
        "duration_ms": duration_ms,
        "error_message": error_message,
        "started_at": started_at,
        "finished_at": utc_now(),
    }
