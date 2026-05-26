from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import db
from .config import default_paths


def handle_command(text: str, db_path: Path | None = None) -> str:
    paths = default_paths()
    target_db = db_path or paths.db
    parts = text.strip().split(maxsplit=2)
    if not parts or parts[0] != "/日报":
        return "支持命令：/日报 今天、/日报 搜索 <关键词>、/日报 收藏 <url>、/日报 健康"
    action = parts[1] if len(parts) > 1 else "今天"
    with db.connect(target_db) as conn:
        if action == "今天":
            since = date.today().isoformat()
            items = db.query_items(conn, since=since, limit=10)
            return format_items(items)
        if action == "搜索" and len(parts) > 2:
            return format_items(db.query_items(conn, keyword=parts[2], limit=10))
        if action == "收藏" and len(parts) > 2:
            item = db.find_item_by_url(conn, parts[2].strip())
            if not item:
                return "未找到该 URL。"
            db.save_item(conn, int(item["id"]), source="lark_bot")
            return f"已收藏：{item['title']}"
        if action == "健康":
            health = db.load_source_health(conn, limit=10)
            if not health:
                return "暂无来源健康数据。"
            return "\n".join(f"- {item['source_name']}: {item['last_status']}" for item in health)
        if action == "本周":
            since = (date.today() - timedelta(days=7)).isoformat()
            return format_items(db.query_items(conn, since=since, limit=10))
    return "未知命令。"


def format_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无条目。"
    return "\n".join(f"- {item['title']}\n  {item['url']}" for item in items)


def run_server(host: str, port: int, db_path: Path | None = None) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if payload.get("challenge"):
                self.respond({"challenge": payload["challenge"]})
                return
            text = extract_text(payload)
            self.respond({"text": handle_command(text, db_path=db_path)})

        def respond(self, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, _format: str, *args: Any) -> None:
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def extract_text(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        try:
            content_payload = json.loads(content)
        except json.JSONDecodeError:
            return content
        return str(content_payload.get("text") or content)
    return str(payload.get("text") or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lark event bot for daily brief")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    run_server(args.host, args.port, db_path=Path(args.db) if args.db else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
