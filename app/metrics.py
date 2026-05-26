from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from . import db


def collect_metrics(conn: Connection) -> dict[str, Any]:
    total_items = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
    plugin_health = db.load_plugin_health(conn)
    source_health = db.load_source_health(conn)
    metrics: dict[str, Any] = {"total_items": int(total_items)}
    for item in plugin_health:
        name = safe_name(item["plugin_name"])
        metrics[f"plugin_health_{name}_last_status"] = item.get("last_status")
        metrics[f"plugin_health_{name}_last_duration_ms"] = int(item.get("last_duration_ms") or 0)
    for item in source_health:
        name = safe_name(item["source_name"])
        metrics[f"source_health_{name}_status"] = item.get("last_status")
        metrics[f"source_health_{name}_last_item_count"] = int(item.get("last_item_count") or 0)
    return metrics


def write_metrics_json(conn: Connection, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(collect_metrics(conn), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def serve_metrics(conn: Connection, host: str = "127.0.0.1", port: int = 9100) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/", "/metrics"}:
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps(collect_metrics(conn), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *args: Any) -> None:
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value).lower()).strip("_")
