from __future__ import annotations

import json
import subprocess
from typing import Any, Sequence


def run_lark(args: Sequence[str], timeout: int = 60) -> str:
    cmd = ["lark-cli", *args]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(message[:1000] or f"lark-cli failed with exit code {result.returncode}")
    return result.stdout


def run_lark_json(args: Sequence[str], timeout: int = 60) -> dict[str, Any]:
    stdout = run_lark(args, timeout=timeout)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("lark-cli returned non-JSON output") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("lark-cli returned non-object JSON")
    if payload.get("ok") is False:
        raise RuntimeError(json.dumps(payload.get("error") or payload, ensure_ascii=False)[:1000])
    return payload
