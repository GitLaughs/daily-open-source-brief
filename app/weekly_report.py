from __future__ import annotations

import html
from datetime import date, timedelta
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from . import db


def build_weekly_report(conn: Connection, *, today: date | None = None) -> str:
    today = today or date.today()
    start = today - timedelta(days=today.weekday())
    since = start.isoformat()
    items = db.query_items(conn, since=since, limit=80)
    high_items = [item for item in items if float(item.get("score") or 0) >= 70][:20]
    saved = load_saved_since(conn, since)
    deadlines = [event for event in db.load_deadline_events(conn, limit=50) if str(event.get("deadline") or "") <= (today + timedelta(days=7)).isoformat()]
    health = db.load_source_health(conn)

    lines = [f"# 周报 {start.isoformat()} 至 {today.isoformat()}"]
    lines.extend(["", "## 本周高优先级通知"])
    lines.extend(format_item(item) for item in high_items) if high_items else lines.append("- 无")
    lines.extend(["", "## 本周新增收藏"])
    lines.extend(format_item(item) for item in saved[:20]) if saved else lines.append("- 无")
    lines.extend(["", "## 未来 7 天截止事项"])
    lines.extend(format_deadline(event) for event in deadlines[:20]) if deadlines else lines.append("- 无")
    abnormal = [item for item in health if item.get("last_status") != "success"]
    lines.extend(["", "## 来源健康异常"])
    lines.extend(f"- {item.get('source_name')}：{item.get('last_error') or item.get('last_status')}" for item in abnormal[:20]) if abnormal else lines.append("- 无")
    return "\n".join(lines)


def write_weekly_report(archive_dir: Path, content: str, *, today: date | None = None) -> Path:
    today = today or date.today()
    year, week, _weekday = today.isocalendar()
    out_dir = archive_dir / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{year}-W{week:02d}.html"
    body = html.escape(content).replace("\n", "<br>\n")
    path.write_text(f"<!doctype html><meta charset=\"utf-8\"><title>周报</title><body>{body}</body>", encoding="utf-8")
    return path


def load_saved_since(conn: Connection, since: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.id, i.source_type, i.title, i.url, i.content_snippet, i.score,
               i.first_seen_at, i.last_seen_at, i.last_notified_slot
        FROM saved_items s
        JOIN items i ON i.id = s.item_id
        WHERE s.created_at >= ?
        ORDER BY s.created_at DESC
        LIMIT 50
        """,
        (since,),
    ).fetchall()
    return [dict(row) for row in rows]


def format_item(item: dict[str, Any]) -> str:
    return f"- {item.get('title')}（{item.get('source_type')}，{float(item.get('score') or 0):.1f}）\n  {item.get('url')}"


def format_deadline(event: dict[str, Any]) -> str:
    return f"- [{event.get('event_type')}] {event.get('title')}：{event.get('deadline')}\n  {event.get('source_url') or ''}"
