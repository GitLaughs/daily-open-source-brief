from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .lark_cli import run_lark_json


DEFAULT_LARK_MAX_CHARS = 3500


def lark_configured() -> bool:
    enabled = os.getenv("LARK_SEND", "").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and bool(os.getenv("LARK_USER_ID") or os.getenv("LARK_CHAT_ID"))


def lark_receive_id() -> str:
    return (os.getenv("LARK_USER_ID") or os.getenv("LARK_CHAT_ID") or "").strip()


def digest_markdown(title: str, text_content: str, archive_path: Optional[Path] = None) -> str:
    full = build_full_markdown(title, text_content, archive_path)
    max_chars = int(os.getenv("LARK_MAX_MARKDOWN_CHARS", str(DEFAULT_LARK_MAX_CHARS)))
    if max_chars <= 0 or len(full) <= max_chars:
        return full
    return build_summary_markdown(title, text_content, archive_path, max_chars)


def build_full_markdown(title: str, text_content: str, archive_path: Optional[Path] = None) -> str:
    lines = [f"## {title}", "", text_content.strip()]
    if archive_path:
        lines.extend(["", f"归档：`{archive_path}`"])
    return "\n".join(lines).strip() + "\n"


def build_summary_markdown(title: str, text_content: str, archive_path: Optional[Path], max_chars: int) -> str:
    priority = extract_priority_section(text_content)
    lines = [f"## {title}", "", priority.strip()]
    if archive_path:
        lines.extend(["", f"完整归档：`{archive_path}`"])
    summary = "\n".join(line for line in lines if line is not None).strip()
    if len(summary) <= max_chars:
        return summary + "\n"
    reserve = 0
    archive_line = ""
    if archive_path:
        archive_line = f"\n\n完整归档：`{archive_path}`"
        reserve = len(archive_line)
    head = f"## {title}\n\n"
    body_limit = max(max_chars - len(head) - reserve - 1, 0)
    result = (head + priority[:body_limit].rstrip() + archive_line).strip()
    if len(result) >= max_chars:
        result = result[: max_chars - 1].rstrip()
    return result + "\n"


def extract_priority_section(text_content: str) -> str:
    lines = text_content.strip().splitlines()
    if not lines:
        return ""
    start = 0
    for index, line in enumerate(lines):
        if line.strip().startswith("## 今日优先处理"):
            start = index
            break
    selected: list[str] = []
    for line in lines[start:]:
        if selected and line.startswith("## "):
            break
        selected.append(line)
    if selected:
        item_count = sum(1 for line in selected if line.strip().startswith("- "))
        if item_count >= 3 or len(selected) >= 8:
            return "\n".join(selected)
    return "\n".join(lines[:20])


def split_markdown(markdown: str, max_chars: int = DEFAULT_LARK_MAX_CHARS) -> list[str]:
    markdown = markdown.strip()
    if not markdown:
        return []
    if max_chars <= 0 or len(markdown) <= max_chars:
        return [markdown + "\n"]

    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    blocks = markdown.split("\n\n")
    for block in blocks:
        block_len = len(block) + (2 if current else 0)
        if current and current_len + block_len > max_chars:
            parts.append("\n\n".join(current).strip() + "\n")
            current = []
            current_len = 0
        if len(block) > max_chars:
            if current:
                parts.append("\n\n".join(current).strip() + "\n")
                current = []
                current_len = 0
            for start in range(0, len(block), max_chars):
                parts.append(block[start : start + max_chars].strip() + "\n")
            continue
        current.append(block)
        current_len += block_len
    if current:
        parts.append("\n\n".join(current).strip() + "\n")
    return parts


def send_lark_message(markdown: str, delivery_slot: str) -> dict[str, Any]:
    max_chars = int(os.getenv("LARK_MAX_MARKDOWN_CHARS", str(DEFAULT_LARK_MAX_CHARS)))
    parts = split_markdown(markdown, max_chars=max_chars)
    if not parts:
        raise RuntimeError("Lark markdown is empty")

    message_ids: list[str] = []
    last_data: dict[str, Any] = {}
    for index, part in enumerate(parts, start=1):
        data = send_lark_message_part(part, delivery_slot, index=index, total=len(parts))
        last_data = data
        message_id = data.get("message_id")
        if message_id:
            message_ids.append(str(message_id))
    return {**last_data, "parts": len(parts), "message_ids": message_ids}


def send_lark_message_part(markdown: str, delivery_slot: str, *, index: int = 1, total: int = 1) -> dict[str, Any]:
    identity = os.getenv("LARK_AS", "bot")
    args = ["im", "+messages-send", "--as", identity, "--markdown", markdown]
    user_id = os.getenv("LARK_USER_ID", "").strip()
    chat_id = os.getenv("LARK_CHAT_ID", "").strip()
    if user_id:
        args.extend(["--user-id", user_id])
    elif chat_id:
        args.extend(["--chat-id", chat_id])
    else:
        raise RuntimeError("Missing LARK_USER_ID or LARK_CHAT_ID")

    suffix = "" if total == 1 else f"-{index}"
    args.extend(["--idempotency-key", f"daily-open-source-brief-{delivery_slot}{suffix}"])
    payload = run_lark_json(args, timeout=60)
    return payload.get("data") or {}
