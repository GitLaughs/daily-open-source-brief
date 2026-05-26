from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA_VERSION = 3

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  url TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  content_snippet TEXT NOT NULL DEFAULT '',
  content_full TEXT,
  raw_json TEXT NOT NULL DEFAULT '{}',
  hash TEXT NOT NULL,
  published_at TEXT,
  fetched_at TEXT NOT NULL,
  first_seen_at TEXT,
  last_seen_at TEXT,
  last_notified_slot TEXT,
  score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'new',
  UNIQUE(source_type, hash)
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
  title,
  content_snippet,
  url,
  source_type
);

CREATE TABLE IF NOT EXISTS item_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL,
  tag TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'local',
  created_at TEXT NOT NULL,
  UNIQUE(item_id, tag)
);

CREATE TABLE IF NOT EXISTS item_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL,
  feedback_type TEXT NOT NULL,
  value INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT 'local',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(item_id, feedback_type)
);

CREATE INDEX IF NOT EXISTS idx_item_tags_item_id ON item_tags(item_id);
CREATE INDEX IF NOT EXISTS idx_item_feedback_item_id ON item_feedback(item_id);
CREATE INDEX IF NOT EXISTS idx_item_feedback_type_value ON item_feedback(feedback_type, value);

CREATE TABLE IF NOT EXISTS deadline_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER,
  title TEXT NOT NULL,
  event_type TEXT NOT NULL,
  deadline TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  location TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  lark_task_id TEXT,
  source_url TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deadline_events_deadline ON deadline_events(deadline);
CREATE INDEX IF NOT EXISTS idx_deadline_events_status ON deadline_events(status);

CREATE TABLE IF NOT EXISTS repo_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  stars INTEGER NOT NULL,
  forks INTEGER NOT NULL,
  open_issues INTEGER NOT NULL,
  language TEXT,
  license TEXT,
  pushed_at TEXT,
  snapshot_date TEXT NOT NULL,
  raw_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(full_name, snapshot_date)
);

CREATE TABLE IF NOT EXISTS digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_date TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  text_content TEXT NOT NULL,
  html_content TEXT NOT NULL,
  item_ids_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_id INTEGER,
  mail_to TEXT,
  subject TEXT NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT,
  sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lark_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_id INTEGER,
  receive_id TEXT NOT NULL,
  subject TEXT NOT NULL,
  delivery_slot TEXT NOT NULL,
  status TEXT NOT NULL,
  message_id TEXT,
  error_message TEXT,
  sent_at TEXT NOT NULL,
  UNIQUE(receive_id, delivery_slot, status)
);

CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url TEXT,
  status TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url TEXT,
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  last_status TEXT NOT NULL,
  last_error TEXT,
  last_item_count INTEGER NOT NULL DEFAULT 0,
  last_duration_ms INTEGER NOT NULL DEFAULT 0,
  last_success_at TEXT,
  last_failure_at TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(source_name, source_type)
);

CREATE TABLE IF NOT EXISTS saved_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL,
  note TEXT,
  source TEXT NOT NULL DEFAULT 'local',
  created_at TEXT NOT NULL,
  UNIQUE(item_id)
);

CREATE TABLE IF NOT EXISTS ignored_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_type TEXT NOT NULL,
  pattern TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(rule_type, pattern)
);

CREATE TABLE IF NOT EXISTS user_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_type TEXT NOT NULL,
  item_id INTEGER,
  payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plugin_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plugin_name TEXT NOT NULL,
  plugin_kind TEXT NOT NULL,
  status TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plugin_health (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plugin_name TEXT NOT NULL UNIQUE,
  plugin_kind TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  last_status TEXT NOT NULL,
  last_error TEXT,
  last_item_count INTEGER NOT NULL DEFAULT 0,
  last_duration_ms INTEGER NOT NULL DEFAULT 0,
  last_success_at TEXT,
  last_failure_at TEXT,
  updated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    ensure_migrations(conn)
    return conn


def ensure_migrations(conn: sqlite3.Connection) -> None:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current < 1:
        migrate_v1(conn)
    if current < 2:
        migrate_v2(conn)
    if current < 3:
        migrate_v3(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    backfill_items_fts(conn)


def migrate_v1(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    for name in ["first_seen_at", "last_seen_at", "last_notified_slot"]:
        if name not in columns:
            conn.execute(f"ALTER TABLE items ADD COLUMN {name} TEXT")
    conn.execute("UPDATE items SET first_seen_at = COALESCE(first_seen_at, fetched_at)")
    conn.execute("UPDATE items SET last_seen_at = COALESCE(last_seen_at, fetched_at)")


def migrate_v2(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deadline_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          item_id INTEGER,
          title TEXT NOT NULL,
          event_type TEXT NOT NULL,
          deadline TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0,
          location TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          lark_task_id TEXT,
          source_url TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deadline_events_deadline ON deadline_events(deadline)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deadline_events_status ON deadline_events(status)")


def migrate_v3(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    if "content_full" not in columns:
        conn.execute("ALTER TABLE items ADD COLUMN content_full TEXT")


def backfill_items_fts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO items_fts(rowid, title, content_snippet, url, source_type)
        SELECT i.id, i.title, i.content_snippet, i.url, i.source_type
        FROM items i
        LEFT JOIN items_fts f ON f.rowid = i.id
        WHERE f.rowid IS NULL
        """
    )


def sync_item_fts(conn: sqlite3.Connection, item_id: int) -> None:
    row = conn.execute(
        """
        SELECT title, content_snippet, url, source_type
        FROM items
        WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    if not row:
        conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
        return
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    conn.execute(
        """
        INSERT INTO items_fts(rowid, title, content_snippet, url, source_type)
        VALUES(?, ?, ?, ?, ?)
        """,
        (
            item_id,
            row["title"] or "",
            row["content_snippet"] or "",
            row["url"] or "",
            row["source_type"] or "",
        ),
    )


def upsert_source(conn: sqlite3.Connection, name: str, source_type: str, config: dict[str, Any]) -> int:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO sources(name, type, url, enabled, config_json, created_at, updated_at)
        VALUES(?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(name, type) DO UPDATE SET
          config_json=excluded.config_json,
          updated_at=excluded.updated_at
        """,
        (name, source_type, config.get("url"), json.dumps(config, ensure_ascii=False), now, now),
    )
    row = conn.execute("SELECT id FROM sources WHERE name=? AND type=?", (name, source_type)).fetchone()
    return int(row["id"])


def upsert_item(conn: sqlite3.Connection, item: dict[str, Any]) -> int:
    seen_at = item.get("fetched_at") or utc_now()
    item.setdefault("first_seen_at", seen_at)
    item["last_seen_at"] = seen_at
    item.setdefault("last_notified_slot", None)
    item.setdefault("content_full", None)
    conn.execute(
        """
        INSERT INTO items(source_id, source_type, title, url, content_snippet, content_full, raw_json, hash,
                          published_at, fetched_at, first_seen_at, last_seen_at, last_notified_slot,
                          score, status)
        VALUES(:source_id, :source_type, :title, :url, :content_snippet, :content_full, :raw_json, :hash,
               :published_at, :fetched_at, :first_seen_at, :last_seen_at, :last_notified_slot,
               :score, :status)
        ON CONFLICT(source_type, hash) DO UPDATE SET
          title=excluded.title,
          url=excluded.url,
          content_snippet=excluded.content_snippet,
          content_full=excluded.content_full,
          raw_json=excluded.raw_json,
          published_at=excluded.published_at,
          fetched_at=excluded.fetched_at,
          last_seen_at=excluded.last_seen_at,
          score=excluded.score,
          status=excluded.status
        """,
        item,
    )
    row = conn.execute(
        "SELECT id FROM items WHERE source_type=? AND hash=?",
        (item["source_type"], item["hash"]),
    ).fetchone()
    item_id = int(row["id"])
    sync_item_fts(conn, item_id)
    return item_id


def upsert_deadline_event(conn: sqlite3.Connection, event: dict[str, Any]) -> int:
    now = utc_now()
    event.setdefault("created_at", now)
    event["updated_at"] = now
    row = conn.execute(
        """
        SELECT id FROM deadline_events
        WHERE item_id IS ? AND title = ? AND event_type = ? AND deadline = ?
        LIMIT 1
        """,
        (event.get("item_id"), event["title"], event["event_type"], event["deadline"]),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE deadline_events
            SET confidence=?, location=?, status=?, lark_task_id=?, source_url=?, updated_at=?
            WHERE id=?
            """,
            (
                float(event.get("confidence") or 0),
                event.get("location"),
                event.get("status") or "pending",
                event.get("lark_task_id"),
                event.get("source_url"),
                event["updated_at"],
                int(row["id"]),
            ),
        )
        return int(row["id"])
    conn.execute(
        """
        INSERT INTO deadline_events(item_id, title, event_type, deadline, confidence,
                                    location, status, lark_task_id, source_url, created_at, updated_at)
        VALUES(:item_id, :title, :event_type, :deadline, :confidence,
               :location, :status, :lark_task_id, :source_url, :created_at, :updated_at)
        """,
        {
            "item_id": event.get("item_id"),
            "title": event["title"],
            "event_type": event["event_type"],
            "deadline": event["deadline"],
            "confidence": float(event.get("confidence") or 0),
            "location": event.get("location"),
            "status": event.get("status") or "pending",
            "lark_task_id": event.get("lark_task_id"),
            "source_url": event.get("source_url"),
            "created_at": event["created_at"],
            "updated_at": event["updated_at"],
        },
    )
    row = conn.execute(
        """
        SELECT id FROM deadline_events
        WHERE item_id IS ? AND title = ? AND event_type = ? AND deadline = ?
        ORDER BY id DESC LIMIT 1
        """,
        (event.get("item_id"), event["title"], event["event_type"], event["deadline"]),
    ).fetchone()
    return int(row["id"])


def load_deadline_events(conn: sqlite3.Connection, *, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if status:
        where = "WHERE status = ?"
        params.append(status)
    rows = conn.execute(
        f"""
        SELECT id, item_id, title, event_type, deadline, confidence, location,
               status, lark_task_id, source_url, created_at, updated_at
        FROM deadline_events
        {where}
        ORDER BY deadline ASC, confidence DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_repo_snapshot(conn: sqlite3.Connection, repo: dict[str, Any], snapshot_date: str) -> None:
    license_obj = repo.get("license") or {}
    conn.execute(
        """
        INSERT INTO repo_snapshots(full_name, stars, forks, open_issues, language, license,
                                   pushed_at, snapshot_date, raw_json)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(full_name, snapshot_date) DO UPDATE SET
          stars=excluded.stars,
          forks=excluded.forks,
          open_issues=excluded.open_issues,
          language=excluded.language,
          license=excluded.license,
          pushed_at=excluded.pushed_at,
          raw_json=excluded.raw_json
        """,
        (
            repo["full_name"],
            int(repo.get("stargazers_count") or 0),
            int(repo.get("forks_count") or 0),
            int(repo.get("open_issues_count") or 0),
            repo.get("language"),
            license_obj.get("spdx_id") if isinstance(license_obj, dict) else None,
            repo.get("pushed_at"),
            snapshot_date,
            json.dumps(repo, ensure_ascii=False),
        ),
    )


def save_digest(
    conn: sqlite3.Connection,
    digest_date: str,
    title: str,
    text_content: str,
    html_content: str,
    item_ids: Iterable[int],
) -> int:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO digests(digest_date, title, text_content, html_content, item_ids_json, created_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(digest_date) DO UPDATE SET
          title=excluded.title,
          text_content=excluded.text_content,
          html_content=excluded.html_content,
          item_ids_json=excluded.item_ids_json,
          created_at=excluded.created_at
        """,
        (digest_date, title, text_content, html_content, json.dumps(list(item_ids)), now),
    )
    row = conn.execute("SELECT id FROM digests WHERE digest_date=?", (digest_date,)).fetchone()
    return int(row["id"])


def load_recent_repos(conn: sqlite3.Connection, limit: int = 60) -> tuple[list[dict[str, Any]], list[int]]:
    rows = conn.execute(
        """
        SELECT id, raw_json, score
        FROM items
        WHERE source_type = 'github_repo'
        ORDER BY fetched_at DESC, score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    repos: list[dict[str, Any]] = []
    item_ids: list[int] = []
    seen: set[str] = set()
    for row in rows:
        try:
            repo = json.loads(row["raw_json"])
        except json.JSONDecodeError:
            continue
        if not isinstance(repo, dict):
            continue
        full_name = str(repo.get("full_name") or "").lower()
        if not full_name or full_name in seen:
            continue
        seen.add(full_name)
        repo["_score"] = float(row["score"] or repo.get("_score") or 0)
        repo["_item_id"] = int(row["id"])
        repos.append(repo)
        item_ids.append(int(row["id"]))
    return repos, item_ids


def load_recent_items(conn: sqlite3.Connection, source_types: Iterable[str], limit: int = 60) -> tuple[list[dict[str, Any]], list[int]]:
    types = [str(item) for item in source_types]
    if not types:
        return [], []
    placeholders = ",".join("?" for _ in types)
    rows = conn.execute(
        f"""
        SELECT id, raw_json, score
        FROM items
        WHERE source_type IN ({placeholders})
        ORDER BY fetched_at DESC, score DESC
        LIMIT ?
        """,
        (*types, limit),
    ).fetchall()
    items: list[dict[str, Any]] = []
    item_ids: list[int] = []
    seen: set[str] = set()
    for row in rows:
        try:
            item = json.loads(row["raw_json"])
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        key = str(item.get("url") or item.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        item["_score"] = float(row["score"] or item.get("_score") or 0)
        item["_item_id"] = int(row["id"])
        items.append(item)
        item_ids.append(int(row["id"]))
    return items, item_ids


def load_recent_web_items(conn: sqlite3.Connection, limit: int = 80) -> tuple[list[dict[str, Any]], list[int]]:
    return load_recent_items(conn, ["school_notice", "webpage_entry", "rss_entry", "industry_news", "tech_news"], limit=limit)


def log_source_run(conn: sqlite3.Connection, run: dict[str, Any]) -> None:
    source_name = str(run["source_name"])
    source_type = str(run["source_type"])
    url = run.get("url")
    status = str(run["status"])
    item_count = int(run.get("item_count") or 0)
    duration_ms = int(run.get("duration_ms") or 0)
    error_message = run.get("error_message")
    started_at = str(run.get("started_at") or utc_now())
    finished_at = str(run.get("finished_at") or utc_now())
    conn.execute(
        """
        INSERT INTO source_runs(source_name, source_type, url, status, item_count,
                                duration_ms, error_message, started_at, finished_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (source_name, source_type, url, status, item_count, duration_ms, error_message, started_at, finished_at),
    )
    success_inc = 1 if status == "success" else 0
    failure_inc = 0 if status == "success" else 1
    last_success_at = finished_at if status == "success" else None
    last_failure_at = finished_at if status != "success" else None
    conn.execute(
        """
        INSERT INTO source_health(source_name, source_type, url, success_count, failure_count,
                                  last_status, last_error, last_item_count, last_duration_ms,
                                  last_success_at, last_failure_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_name, source_type) DO UPDATE SET
          url=excluded.url,
          success_count=source_health.success_count + ?,
          failure_count=source_health.failure_count + ?,
          last_status=excluded.last_status,
          last_error=excluded.last_error,
          last_item_count=excluded.last_item_count,
          last_duration_ms=excluded.last_duration_ms,
          last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at),
          last_failure_at=COALESCE(excluded.last_failure_at, source_health.last_failure_at),
          updated_at=excluded.updated_at
        """,
        (
            source_name,
            source_type,
            url,
            success_inc,
            failure_inc,
            status,
            error_message,
            item_count,
            duration_ms,
            last_success_at,
            last_failure_at,
            finished_at,
            success_inc,
            failure_inc,
        ),
    )


def log_source_runs(conn: sqlite3.Connection, runs: Iterable[dict[str, Any]]) -> None:
    for run in runs:
        log_source_run(conn, run)


def load_source_health(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source_name, source_type, url, success_count, failure_count, last_status,
               last_error, last_item_count, last_duration_ms, last_success_at,
               last_failure_at, updated_at
        FROM source_health
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def log_plugin_run(
    conn: sqlite3.Connection,
    *,
    plugin_name: str,
    plugin_kind: str,
    status: str,
    item_count: int,
    duration_ms: int,
    error_message: Optional[str],
    started_at: str,
    finished_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO plugin_runs(plugin_name, plugin_kind, status, item_count,
                                duration_ms, error_message, started_at, finished_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (plugin_name, plugin_kind, status, item_count, duration_ms, error_message, started_at, finished_at),
    )
    success_inc = 1 if status == "success" else 0
    failure_inc = 1 if status == "failed" else 0
    skipped_inc = 1 if status == "skipped" else 0
    last_success_at = finished_at if status == "success" else None
    last_failure_at = finished_at if status == "failed" else None
    conn.execute(
        """
        INSERT INTO plugin_health(plugin_name, plugin_kind, enabled, success_count,
                                  failure_count, skipped_count, last_status, last_error,
                                  last_item_count, last_duration_ms, last_success_at,
                                  last_failure_at, updated_at)
        VALUES(?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(plugin_name) DO UPDATE SET
          plugin_kind=excluded.plugin_kind,
          success_count=plugin_health.success_count + ?,
          failure_count=plugin_health.failure_count + ?,
          skipped_count=plugin_health.skipped_count + ?,
          last_status=excluded.last_status,
          last_error=excluded.last_error,
          last_item_count=excluded.last_item_count,
          last_duration_ms=excluded.last_duration_ms,
          last_success_at=COALESCE(excluded.last_success_at, plugin_health.last_success_at),
          last_failure_at=COALESCE(excluded.last_failure_at, plugin_health.last_failure_at),
          updated_at=excluded.updated_at
        """,
        (
            plugin_name,
            plugin_kind,
            success_inc,
            failure_inc,
            skipped_inc,
            status,
            error_message,
            int(item_count or 0),
            int(duration_ms or 0),
            last_success_at,
            last_failure_at,
            finished_at,
            success_inc,
            failure_inc,
            skipped_inc,
        ),
    )


def set_plugin_health_enabled(conn: sqlite3.Connection, plugin_name: str, plugin_kind: str, enabled: bool) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO plugin_health(plugin_name, plugin_kind, enabled, last_status, updated_at)
        VALUES(?, ?, ?, 'never_run', ?)
        ON CONFLICT(plugin_name) DO UPDATE SET
          plugin_kind=excluded.plugin_kind,
          enabled=excluded.enabled,
          updated_at=excluded.updated_at
        """,
        (plugin_name, plugin_kind, 1 if enabled else 0, now),
    )


def load_plugin_health(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT plugin_name, plugin_kind, enabled, success_count, failure_count,
               skipped_count, last_status, last_error, last_item_count,
               last_duration_ms, last_success_at, last_failure_at, updated_at
        FROM plugin_health
        ORDER BY plugin_kind, plugin_name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def find_item_by_url(conn: sqlite3.Connection, url: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        """
        SELECT id, source_type, title, url, content_snippet, score, status,
               first_seen_at, last_seen_at, last_notified_slot
        FROM items
        WHERE url = ?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (url,),
    ).fetchone()
    return dict(row) if row else None


def query_items(
    conn: sqlite3.Connection,
    *,
    keyword: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if keyword:
        clauses.append("(title LIKE ? OR content_snippet LIKE ? OR url LIKE ?)")
        pattern = f"%{keyword}%"
        params.extend([pattern, pattern, pattern])
    if since:
        clauses.append("COALESCE(first_seen_at, fetched_at) >= ?")
        params.append(since)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT id, source_type, title, url, content_snippet, score, status,
               first_seen_at, last_seen_at, last_notified_slot
        FROM items
        {where}
        ORDER BY COALESCE(first_seen_at, fetched_at) DESC, score DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def save_item(conn: sqlite3.Connection, item_id: int, note: str = "", source: str = "local") -> int:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO saved_items(item_id, note, source, created_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
          note=excluded.note,
          source=excluded.source
        """,
        (item_id, note, source, now),
    )
    log_user_action(conn, "save", item_id=item_id, payload={"note": note}, source=source)
    row = conn.execute("SELECT id FROM saved_items WHERE item_id=?", (item_id,)).fetchone()
    return int(row["id"])


def add_ignored_rule(conn: sqlite3.Connection, rule_type: str, pattern: str) -> int:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO ignored_rules(rule_type, pattern, enabled, created_at)
        VALUES(?, ?, 1, ?)
        ON CONFLICT(rule_type, pattern) DO UPDATE SET enabled=1
        """,
        (rule_type, pattern, now),
    )
    log_user_action(conn, "ignore_rule", payload={"rule_type": rule_type, "pattern": pattern}, source="local")
    row = conn.execute(
        "SELECT id FROM ignored_rules WHERE rule_type=? AND pattern=?",
        (rule_type, pattern),
    ).fetchone()
    return int(row["id"])


def load_ignored_rules(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, rule_type, pattern, enabled, created_at
        FROM ignored_rules
        WHERE enabled = 1
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def log_user_action(
    conn: sqlite3.Connection,
    action_type: str,
    *,
    item_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
    source: str = "local",
) -> None:
    conn.execute(
        """
        INSERT INTO user_actions(action_type, item_id, payload_json, source, created_at)
        VALUES(?, ?, ?, ?, ?)
        """,
        (action_type, item_id, json.dumps(payload or {}, ensure_ascii=False), source, utc_now()),
    )


def digest_already_sent(conn: sqlite3.Connection, digest_date: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM digests d
        JOIN mail_logs m ON m.digest_id = d.id
        WHERE d.digest_date = ? AND m.status = 'sent'
        LIMIT 1
        """,
        (digest_date,),
    ).fetchone()
    return row is not None


def mail_already_sent(conn: sqlite3.Connection, digest_date: str) -> bool:
    return digest_already_sent(conn, digest_date)


def lark_already_sent(conn: sqlite3.Connection, receive_id: str, delivery_slot: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM lark_logs
        WHERE receive_id = ? AND delivery_slot = ? AND status = 'sent'
        LIMIT 1
        """,
        (receive_id, delivery_slot),
    ).fetchone()
    return row is not None


def mark_items_notified(conn: sqlite3.Connection, item_ids: Iterable[int], delivery_slot: str) -> int:
    ids = [int(item_id) for item_id in item_ids]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    cursor = conn.execute(
        f"UPDATE items SET last_notified_slot=? WHERE id IN ({placeholders})",
        (delivery_slot, *ids),
    )
    return int(cursor.rowcount)


def load_item_notification_meta(conn: sqlite3.Connection, item_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    ids = [int(item_id) for item_id in item_ids if item_id is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT id, first_seen_at, last_seen_at, fetched_at, last_notified_slot, score
        FROM items
        WHERE id IN ({placeholders})
        """,
        ids,
    ).fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def log_mail(
    conn: sqlite3.Connection,
    digest_id: int,
    mail_to: Optional[str],
    subject: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO mail_logs(digest_id, mail_to, subject, status, error_message, sent_at)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (digest_id, mail_to, subject, status, error_message, utc_now()),
    )


def log_lark(
    conn: sqlite3.Connection,
    digest_id: int,
    receive_id: str,
    subject: str,
    delivery_slot: str,
    status: str,
    message_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO lark_logs(digest_id, receive_id, subject, delivery_slot, status,
                                        message_id, error_message, sent_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (digest_id, receive_id, subject, delivery_slot, status, message_id, error_message, utc_now()),
    )
