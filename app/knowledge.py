from __future__ import annotations

import re
import sqlite3
from typing import Any, Iterable

from . import db


VALID_MARKS = {"favorite", "read", "later", "blocked", "not_interested"}
MARK_ALIASES = {
    "save": "favorite",
    "saved": "favorite",
    "block": "blocked",
    "ignore": "not_interested",
}


def normalize_mark(mark: str) -> str:
    normalized = mark.strip().lower().replace("-", "_")
    normalized = MARK_ALIASES.get(normalized, normalized)
    if normalized not in VALID_MARKS:
        allowed = ", ".join(sorted(VALID_MARKS))
        raise ValueError(f"unknown mark: {mark}. allowed: {allowed}")
    return normalized


def search_items(conn: sqlite3.Connection, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    query = build_fts_query(keyword)
    if not query:
        return list_recent_items(conn, limit=limit)
    rows = conn.execute(
        """
        SELECT i.id, i.source_type, i.title, i.url, i.content_snippet, i.score, i.status,
               i.first_seen_at, i.last_seen_at, i.last_notified_slot,
               bm25(items_fts) AS search_rank
        FROM items_fts
        JOIN items i ON i.id = items_fts.rowid
        WHERE items_fts MATCH ?
        ORDER BY search_rank ASC, i.score DESC, COALESCE(i.last_seen_at, i.fetched_at) DESC
        LIMIT ?
        """,
        (query, int(limit)),
    ).fetchall()
    return decorate_items(conn, [dict(row) for row in rows])


def list_recent_items(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, source_type, title, url, content_snippet, score, status,
               first_seen_at, last_seen_at, last_notified_slot
        FROM items
        ORDER BY COALESCE(last_seen_at, fetched_at) DESC, score DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return decorate_items(conn, [dict(row) for row in rows])


def list_saved_items(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.id, i.source_type, i.title, i.url, i.content_snippet, i.score, i.status,
               i.first_seen_at, i.last_seen_at, i.last_notified_slot,
               MAX(COALESCE(f.updated_at, s.created_at, i.last_seen_at, i.fetched_at)) AS saved_at
        FROM items i
        LEFT JOIN item_feedback f
          ON f.item_id = i.id
         AND f.feedback_type IN ('favorite', 'later')
         AND f.value = 1
        LEFT JOIN saved_items s ON s.item_id = i.id
        WHERE f.id IS NOT NULL OR s.id IS NOT NULL
        GROUP BY i.id
        ORDER BY saved_at DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return decorate_items(conn, [dict(row) for row in rows])


def mark_item(
    conn: sqlite3.Connection,
    item_id: int,
    mark: str,
    value: bool = True,
    source: str = "local",
) -> dict[str, Any]:
    item_id = int(item_id)
    mark_type = normalize_mark(mark)
    ensure_item_exists(conn, item_id)
    now = db.utc_now()
    conn.execute(
        """
        INSERT INTO item_feedback(item_id, feedback_type, value, source, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id, feedback_type) DO UPDATE SET
          value=excluded.value,
          source=excluded.source,
          updated_at=excluded.updated_at
        """,
        (item_id, mark_type, 1 if value else 0, source, now, now),
    )
    db.log_user_action(
        conn,
        f"mark_{mark_type}",
        item_id=item_id,
        payload={"value": bool(value)},
        source=source,
    )
    return dict(
        conn.execute(
            """
            SELECT item_id, feedback_type, value, source, created_at, updated_at
            FROM item_feedback
            WHERE item_id = ? AND feedback_type = ?
            """,
            (item_id, mark_type),
        ).fetchone()
    )


def tag_item(conn: sqlite3.Connection, item_id: int, tag: str, source: str = "local") -> dict[str, Any]:
    item_id = int(item_id)
    normalized = normalize_tag(tag)
    ensure_item_exists(conn, item_id)
    now = db.utc_now()
    conn.execute(
        """
        INSERT INTO item_tags(item_id, tag, source, created_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(item_id, tag) DO NOTHING
        """,
        (item_id, normalized, source, now),
    )
    db.log_user_action(conn, "tag", item_id=item_id, payload={"tag": normalized}, source=source)
    return dict(
        conn.execute(
            """
            SELECT item_id, tag, source, created_at
            FROM item_tags
            WHERE item_id = ? AND tag = ?
            """,
            (item_id, normalized),
        ).fetchone()
    )


def feedback_sorting_hints(conn: sqlite3.Connection) -> dict[str, list[str]]:
    favorite_tags = conn.execute(
        """
        SELECT DISTINCT t.tag
        FROM item_tags t
        JOIN item_feedback f ON f.item_id = t.item_id
        WHERE f.feedback_type = 'favorite' AND f.value = 1
        ORDER BY t.tag
        """
    ).fetchall()
    blocked_keywords = conn.execute(
        """
        SELECT pattern
        FROM ignored_rules
        WHERE enabled = 1 AND rule_type = 'keyword'
        ORDER BY created_at DESC
        """
    ).fetchall()
    disliked_sources = conn.execute(
        """
        SELECT DISTINCT i.source_type
        FROM item_feedback f
        JOIN items i ON i.id = f.item_id
        WHERE f.feedback_type = 'not_interested' AND f.value = 1
        ORDER BY i.source_type
        """
    ).fetchall()
    return {
        "favorite_tags": [row["tag"] for row in favorite_tags],
        "blocked_keywords": [row["pattern"] for row in blocked_keywords],
        "disliked_sources": [row["source_type"] for row in disliked_sources],
    }


def build_fts_query(keyword: str) -> str:
    tokens = re.findall(r"[\w]+", keyword, flags=re.UNICODE)
    return " ".join(f'"{token.replace(chr(34), chr(34) + chr(34))}"' for token in tokens)


def normalize_tag(tag: str) -> str:
    normalized = tag.strip().lower()
    if not normalized:
        raise ValueError("tag must not be empty")
    return normalized


def ensure_item_exists(conn: sqlite3.Connection, item_id: int) -> None:
    row = conn.execute("SELECT 1 FROM items WHERE id = ?", (int(item_id),)).fetchone()
    if not row:
        raise ValueError(f"item not found: {item_id}")


def decorate_items(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [int(item["id"]) for item in items]
    if not ids:
        return items
    tags = load_tags(conn, ids)
    feedback = load_feedback(conn, ids)
    for item in items:
        item_id = int(item["id"])
        item["tags"] = tags.get(item_id, [])
        item["feedback"] = feedback.get(item_id, {})
    return items


def load_tags(conn: sqlite3.Connection, item_ids: Iterable[int]) -> dict[int, list[str]]:
    ids = [int(item_id) for item_id in item_ids]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT item_id, tag
        FROM item_tags
        WHERE item_id IN ({placeholders})
        ORDER BY tag
        """,
        ids,
    ).fetchall()
    tags: dict[int, list[str]] = {}
    for row in rows:
        tags.setdefault(int(row["item_id"]), []).append(row["tag"])
    return tags


def load_feedback(conn: sqlite3.Connection, item_ids: Iterable[int]) -> dict[int, dict[str, bool]]:
    ids = [int(item_id) for item_id in item_ids]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT item_id, feedback_type, value
        FROM item_feedback
        WHERE item_id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    feedback: dict[int, dict[str, bool]] = {}
    for row in rows:
        feedback.setdefault(int(row["item_id"]), {})[row["feedback_type"]] = bool(row["value"])
    return feedback
