from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Sequence

from . import db, knowledge
from .config import default_paths


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query and manage daily brief feedback")
    subparsers = parser.add_subparsers(dest="command", required=True)

    today = subparsers.add_parser("today", help="List items first seen today")
    today.add_argument("--limit", type=int, default=20)

    recent = subparsers.add_parser("recent", help="List recent items")
    recent.add_argument("--days", type=int, default=7)
    recent.add_argument("--limit", type=int, default=20)

    search = subparsers.add_parser("search", help="Search stored items")
    search.add_argument("keyword")
    search.add_argument("--limit", type=int, default=20)

    save = subparsers.add_parser("save", help="Save an item by URL")
    save.add_argument("--url", required=True)
    save.add_argument("--note", default="")

    ignore = subparsers.add_parser("ignore", help="Add an enabled ignore rule")
    ignore.add_argument("--keyword", required=True)

    health = subparsers.add_parser("health", help="Show source health")
    health.add_argument("--limit", type=int, default=20)

    return parser.parse_args(argv)


def today_start() -> str:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).isoformat(timespec="seconds")


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def format_item(item: dict) -> str:
    score = float(item.get("score") or 0)
    seen_at = item.get("first_seen_at") or item.get("last_seen_at") or ""
    return f"[{item['id']}] {item['title']} | {item['source_type']} | {score:.1f} | {seen_at}\n{item['url']}"


def print_items(items: list[dict]) -> None:
    if not items:
        print("No items found.")
        return
    for item in items:
        print(format_item(item))
        print()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = default_paths()
    with db.connect(paths.db) as conn:
        if args.command == "today":
            print_items(db.query_items(conn, since=today_start(), limit=args.limit))
            return 0
        if args.command == "recent":
            print_items(db.query_items(conn, since=days_ago(args.days), limit=args.limit))
            return 0
        if args.command == "search":
            print_items(knowledge.search_items(conn, args.keyword, limit=args.limit))
            return 0
        if args.command == "save":
            item = db.find_item_by_url(conn, args.url)
            if not item:
                print(f"Item not found: {args.url}")
                return 2
            saved_id = db.save_item(conn, int(item["id"]), note=args.note, source="brief_cli")
            knowledge.mark_item(conn, int(item["id"]), "favorite", source="brief_cli")
            print(f"Saved item {item['id']} as saved record {saved_id}: {item['title']}")
            return 0
        if args.command == "ignore":
            rule_id = db.add_ignored_rule(conn, "keyword", args.keyword)
            print(f"Enabled ignore rule {rule_id}: keyword={args.keyword}")
            return 0
        if args.command == "health":
            rows = db.load_source_health(conn, limit=args.limit)
            if not rows:
                print("No source health records.")
                return 0
            for row in rows:
                status = row.get("last_status") or "unknown"
                count = int(row.get("last_item_count") or 0)
                duration = int(row.get("last_duration_ms") or 0)
                error = row.get("last_error") or ""
                print(f"{row['source_name']} | {row['source_type']} | {status} | {count} items | {duration} ms | {error}")
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
