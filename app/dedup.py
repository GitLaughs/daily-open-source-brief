from __future__ import annotations

from typing import Any


def char_bigrams(text: str) -> set[str]:
    normalized = "".join(str(text).lower().split())
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[i : i + 2] for i in range(len(normalized) - 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def dedupe_cross_source(items: list[dict[str, Any]], threshold: float = 0.6) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_titles: list[set[str]] = []
    for item in items:
        title_tokens = char_bigrams(str(item.get("title") or ""))
        if title_tokens and any(jaccard(title_tokens, seen) >= threshold for seen in seen_titles):
            item["deduped_cross_source"] = True
            continue
        seen_titles.append(title_tokens)
        result.append(item)
    return result
