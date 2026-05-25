from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def run_json(cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout).strip()}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "non-json output"}
    return data if isinstance(data, dict) else {"ok": False, "error": "unexpected output"}


def build_profile(config_path: Path, user_id: str) -> dict[str, Any]:
    profile = run_json(["lark-cli", "contact", "+get-user", "--as", "bot", "--user-id", user_id])
    chats = run_json(["lark-cli", "im", "+chat-list", "--as", "user", "--page-size", "20"])
    user = ((profile.get("data") or {}).get("user") or {}) if profile.get("ok") else {}
    chat_names = [
        item.get("name")
        for item in (((chats.get("data") or {}).get("chats") or []) if chats.get("ok") else [])
        if item.get("name")
    ]
    inferred_topics = ["ai", "developer-tools", "automation", "cli", "self-hosted", "infra"]
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lark_user": {
            "name": user.get("name"),
            "open_id": user.get("open_id") or user_id,
            "job_title": user.get("job_title") or "",
            "department_ids": user.get("department_ids") or [],
            "is_tenant_manager": user.get("is_tenant_manager"),
        },
        "signals": {
            "visible_chat_names": chat_names,
        },
        "preferences": {
            "topics": sorted(set(inferred_topics)),
            "languages": ["Python", "TypeScript", "Go", "Rust", "JavaScript"],
            "summary_style": "中文、短句，突出工具可用性、自托管价值和可动手尝试方向",
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return data


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build daily brief preference profile from Lark")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--out", default="config/profile.yml")
    args = parser.parse_args()
    data = build_profile(Path(args.out), args.user_id)
    print(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
