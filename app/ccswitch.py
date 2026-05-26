from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


DEFAULT_MODEL = "gpt-5.5"


def configure_from_ccswitch(force_fallback: bool = False) -> Optional[dict[str, Any]]:
    if os.getenv("LLM_FROM_CCSWITCH", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    selected = select_provider(force_fallback=force_fallback)
    os.environ["OPENAI_API_KEY"] = selected["key"]
    os.environ["OPENAI_BASE_URL"] = selected.get("codex_base_url") or selected["base_url"].rstrip("/")
    os.environ["OPENAI_MODEL"] = selected["model"] or DEFAULT_MODEL
    return public_provider_info(selected)


def select_provider(force_fallback: bool = False) -> dict[str, Any]:
    db_path = Path(os.getenv("CCSWITCH_DB", "~/.cc-switch/cc-switch.db")).expanduser()
    fallback_path = Path(os.getenv("CCSWITCH_FALLBACK_FILE", "~/.cc-switch/mimo-codex-provider.json")).expanduser()
    timeout = float(os.getenv("CCSWITCH_TIMEOUT", "10"))
    min_balance = float(os.getenv("CCSWITCH_MIN_BALANCE", "0"))
    fallback_min_balance = float(os.getenv("CCSWITCH_FALLBACK_MIN_BALANCE", "0"))
    warmup = os.getenv("CCSWITCH_NO_WARMUP", "").strip().lower() not in {"1", "true", "yes", "on"}

    errors: list[str] = []
    if not force_fallback:
        try:
            providers = load_providers(db_path)
            results = evaluate(providers, timeout=timeout, min_balance=min_balance, warmup=warmup, allow_zero_balance=False)
            if results:
                return results[0]
        except Exception as exc:
            errors.append(f"cc-switch primary failed: {type(exc).__name__}: {exc}")

    try:
        fallback_providers = load_fallback_providers(fallback_path)
        fallback_results = evaluate(
            fallback_providers,
            timeout=timeout,
            min_balance=fallback_min_balance,
            warmup=warmup,
            allow_zero_balance=True,
        )
        if fallback_results:
            fallback_results[0]["fallback_reason"] = "; ".join(errors) if errors else "no primary provider with sufficient balance"
            return fallback_results[0]
    except Exception as exc:
        errors.append(f"fallback failed: {type(exc).__name__}: {exc}")

    raise RuntimeError("No usable cc-switch or fallback provider found. " + "; ".join(errors))


def public_provider_info(selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": selected["id"],
        "name": selected["name"],
        "model": os.environ["OPENAI_MODEL"],
        "base_url": os.environ["OPENAI_BASE_URL"],
        "remaining": selected.get("remaining"),
        "kind": selected.get("kind", "db"),
        "fallback_reason": selected.get("fallback_reason"),
    }


def load_providers(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise RuntimeError(f"cc-switch DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, name, settings_config, website_url, sort_index, meta
            FROM providers
            WHERE app_type = 'codex'
            ORDER BY sort_index, name
            """
        ).fetchall()
    finally:
        conn.close()

    providers: list[dict[str, Any]] = []
    for row in rows:
        settings = parse_json_object(row["settings_config"])
        meta = parse_json_object(row["meta"])
        key = extract_api_key(settings, meta)
        config = settings.get("config", "")
        usage_config = meta.get("usage_script") if isinstance(meta.get("usage_script"), dict) else {}
        base_url = usage_config.get("baseUrl") or extract_base_url(config) or row["website_url"]
        model = extract_model(config) or DEFAULT_MODEL
        warmup_api = usage_config.get("warmupApi") or usage_config.get("warmup_api") or "responses"
        if key and base_url:
            providers.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "key": key,
                    "base_url": str(base_url).rstrip("/"),
                    "model": model,
                    "warmup_api": warmup_api,
                    "sort_index": int(row["sort_index"] or 0),
                }
            )
    return providers


def load_fallback_providers(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid fallback provider file: {path}") from exc
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        items = []
    providers: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("api_key") or item.get("OPENAI_API_KEY")
        base_url = item.get("base_url") or item.get("codex_base_url")
        if not key or not base_url:
            continue
        providers.append(
            {
                "id": item.get("id") or f"fallback-{idx}",
                "name": item.get("name") or f"fallback-{idx}",
                "key": str(key).strip(),
                "base_url": str(base_url).rstrip("/"),
                "codex_base_url": str(item.get("codex_base_url") or base_url).rstrip("/"),
                "model": item.get("model") or DEFAULT_MODEL,
                "warmup_api": item.get("warmup_api") or "chat",
                "sort_index": int(item.get("sort_index") or 9999),
                "kind": "fallback",
            }
        )
    return providers


def parse_json_object(text: Optional[str]) -> dict[str, Any]:
    try:
        data = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def extract_api_key(settings: dict[str, Any], meta: dict[str, Any]) -> Optional[str]:
    usage_config = meta.get("usage_script") if isinstance(meta.get("usage_script"), dict) else {}
    candidates: list[Any] = [
        usage_config.get("apiKey"),
        settings.get("api_key"),
        settings.get("OPENAI_API_KEY"),
    ]
    auth = settings.get("auth")
    if isinstance(auth, dict):
        candidates.extend([auth.get("OPENAI_API_KEY"), auth.get("apiKey"), auth.get("key")])
    elif isinstance(auth, str):
        candidates.append(auth)
    env = settings.get("env")
    if isinstance(env, dict):
        candidates.extend([env.get("OPENAI_API_KEY"), env.get("ANTHROPIC_AUTH_TOKEN")])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_base_url(config_text: str) -> Optional[str]:
    for line in str(config_text).splitlines():
        stripped = line.strip()
        if stripped.startswith("base_url"):
            _, value = stripped.split("=", 1)
            return value.strip().strip('"').strip("'")
    return None


def extract_model(config_text: str) -> Optional[str]:
    for line in str(config_text).splitlines():
        stripped = line.strip()
        if stripped.startswith("model ="):
            _, value = stripped.split("=", 1)
            return value.strip().strip('"').strip("'")
    return None


def evaluate(
    providers: list[dict[str, Any]],
    timeout: float,
    min_balance: float,
    warmup: bool,
    allow_zero_balance: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for provider in providers:
        usage = query_usage(provider, timeout=timeout, warmup=warmup)
        item = {**provider, **usage}
        remaining = float(item.get("remaining") or 0)
        if item.get("ok") and (remaining >= min_balance or allow_zero_balance):
            candidates.append(item)
    candidates.sort(key=lambda item: (float(item.get("remaining") or 0), -int(item.get("sort_index") or 0)), reverse=True)
    return candidates


def api_url(provider: dict[str, Any], path: str) -> str:
    base = provider["base_url"].rstrip("/")
    if base.endswith("/v1") and path.startswith("/v1/"):
        return base + path[3:]
    if not base.endswith("/v1") and not path.startswith("/v1/"):
        path = "/v1/" + path.lstrip("/")
    return base + path


def query_usage(provider: dict[str, Any], timeout: float, warmup: bool) -> dict[str, Any]:
    warm_ok = False
    if warmup:
        warm = warmup_provider(provider, timeout)
        if not warm.get("ok"):
            return warm
        warm_ok = True
        time.sleep(0.8)

    req = urllib.request.Request(
        api_url(provider, "/v1/usage"),
        headers={"Authorization": "Bearer " + provider["key"], "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if provider.get("kind") == "fallback" and exc.code not in {401, 403} and (warm_ok or not warmup):
            return {"ok": True, "remaining": 0.0, "valid": True, "balance_note": f"usage unavailable: http {exc.code}"}
        return {"ok": False, "error": f"HTTP Error {exc.code}: {exc.reason}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        if provider.get("kind") == "fallback" and warm_ok:
            return {"ok": True, "remaining": 0.0, "valid": True, "balance_note": "usage unavailable after warmup"}
        return {"ok": False, "error": str(exc)}

    remaining = first_number(data, [("remaining",), ("quota", "remaining"), ("balance",), ("data", "remaining"), ("data", "balance"), ("data", "totalBalance")])
    valid = normalize_valid(first_value(data, [("is_active",), ("isValid",), ("is_valid",), ("data", "is_active"), ("data", "isValid"), ("data", "status")]))
    if remaining is None:
        return {"ok": valid, "remaining": 0.0, "valid": valid}
    return {"ok": valid and remaining > 0, "remaining": remaining, "valid": valid}


def warmup_provider(provider: dict[str, Any], timeout: float) -> dict[str, Any]:
    if provider.get("warmup_api") == "chat":
        return warmup_chat(provider, timeout)
    payload = json.dumps({"model": provider.get("model") or DEFAULT_MODEL, "input": "ping", "max_output_tokens": 8}).encode()
    req = urllib.request.Request(
        api_url(provider, "/v1/responses"),
        data=payload,
        headers={"Authorization": "Bearer " + provider["key"], "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(4096)
        return {"ok": True}
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 404, 405, 422}:
            return warmup_chat(provider, timeout)
        return {"ok": False, "error": f"warmup http {exc.code}: {exc.reason}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": "warmup " + str(exc)}


def warmup_chat(provider: dict[str, Any], timeout: float) -> dict[str, Any]:
    payload = json.dumps({"model": provider.get("model") or DEFAULT_MODEL, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8}).encode()
    req = urllib.request.Request(
        api_url(provider, "/v1/chat/completions"),
        data=payload,
        headers={"Authorization": "Bearer " + provider["key"], "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read(4096)
        return {"ok": True}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"warmup chat http {exc.code}: {exc.reason}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "error": "warmup chat " + str(exc)}


def first_value(data: dict[str, Any], paths: list[tuple[str, ...]]) -> Any:
    for path in paths:
        node: Any = data
        for part in path:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is not None:
            return node
    return None


def first_number(data: dict[str, Any], paths: list[tuple[str, ...]]) -> Optional[float]:
    value = first_value(data, paths)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_valid(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "inactive", "disabled", "expired"}
    return True
