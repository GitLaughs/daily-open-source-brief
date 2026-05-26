from __future__ import annotations

from dataclasses import dataclass, field
from sqlite3 import Connection
from typing import Any

from . import db


@dataclass(frozen=True)
class FeedbackWeights:
    favorite_tags: set[str] = field(default_factory=set)
    blocked_keywords: set[str] = field(default_factory=set)
    disliked_sources: set[str] = field(default_factory=set)
    favorite_boost: float = 15.0
    blocked_penalty: float = -100.0
    disliked_penalty: float = -20.0


def load_feedback_weights(conn: Connection) -> FeedbackWeights:
    favorite_tags = {
        str(row["tag"]).lower()
        for row in conn.execute(
            """
            SELECT DISTINCT t.tag
            FROM item_tags t
            JOIN item_feedback f ON f.item_id = t.item_id
            WHERE f.feedback_type IN ('favorite', 'saved', 'useful') AND f.value = 1
            """
        ).fetchall()
    }
    disliked_sources = {
        str(row["source_type"]).lower()
        for row in conn.execute(
            """
            SELECT DISTINCT i.source_type
            FROM items i
            JOIN item_feedback f ON f.item_id = i.id
            WHERE f.feedback_type IN ('not_interested', 'dislike') AND f.value = 1
            """
        ).fetchall()
    }
    blocked_keywords = {
        str(rule["pattern"]).lower()
        for rule in db.load_ignored_rules(conn)
        if str(rule.get("rule_type") or "").lower() in {"keyword", "title", "text"}
    }
    return FeedbackWeights(
        favorite_tags={tag for tag in favorite_tags if tag},
        blocked_keywords={keyword for keyword in blocked_keywords if keyword},
        disliked_sources={source for source in disliked_sources if source},
    )


def apply_feedback_score(base_score: float, entry: dict[str, Any], weights: FeedbackWeights) -> tuple[float, list[str]]:
    score = float(base_score or 0)
    reasons: list[str] = []
    text = f"{entry.get('title', '')} {entry.get('content_snippet', '')} {entry.get('description', '')}".lower()
    tags = {str(tag).lower() for tag in entry.get("tags") or entry.get("topics") or []}
    source_type = str(entry.get("source_type") or "github_repo").lower()

    matched_tags = sorted(tags & weights.favorite_tags)
    if matched_tags:
        score += weights.favorite_boost
        reasons.append("favorite_tags:" + ",".join(matched_tags[:5]))

    matched_keywords = sorted(keyword for keyword in weights.blocked_keywords if keyword in text)
    if matched_keywords:
        score += weights.blocked_penalty
        entry["filtered_by_feedback"] = True
        reasons.append("blocked_keywords:" + ",".join(matched_keywords[:5]))

    if source_type in weights.disliked_sources:
        score += weights.disliked_penalty
        reasons.append(f"disliked_source:{source_type}")

    return round(score, 2), reasons
