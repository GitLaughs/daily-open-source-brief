from __future__ import annotations

import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from .. import db
from ..config import load_yaml_config
from .base import BasePlugin, PluginContext, PluginResult
from .registry import PluginRegistry, default_order


DEFAULT_PLUGINS: dict[str, dict[str, Any]] = {
    "ccswitch": {"kind": "provider", "enabled": True},
    "github": {"kind": "collector", "enabled": True, "limit": 40},
    "github_trending": {"kind": "collector", "enabled": False, "limit": 10},
    "webpage": {"kind": "collector", "enabled": True},
    "rss": {"kind": "collector", "enabled": True},
    "feedback": {"kind": "enricher", "enabled": True},
    "deadline": {"kind": "enricher", "enabled": True},
    "cross_source_dedupe": {"kind": "enricher", "enabled": False},
    "lark_digest": {"kind": "enricher", "enabled": True},
    "summarizer": {"kind": "summarizer", "enabled": True},
    "renderer": {"kind": "renderer", "enabled": True},
    "lark": {"kind": "sender", "enabled": True},
    "mail": {"kind": "sender", "enabled": True},
    "webhook": {"kind": "sender", "enabled": False},
}


def load_plugin_settings(path: Path) -> dict[str, dict[str, Any]]:
    raw = load_yaml_config(path).get("plugins", {})
    settings: dict[str, dict[str, Any]] = {name: dict(config) for name, config in DEFAULT_PLUGINS.items()}
    if isinstance(raw, dict):
        for name, config in raw.items():
            if not isinstance(config, dict):
                continue
            settings.setdefault(str(name), {}).update(config)
    return settings


class PluginManager:
    def __init__(self, settings: dict[str, dict[str, Any]]) -> None:
        self.settings = settings
        self.plugins: OrderedDict[str, BasePlugin] = OrderedDict()

    @classmethod
    def from_registry(cls, registry: PluginRegistry, settings: dict[str, dict[str, Any]]) -> "PluginManager":
        manager = cls(settings)
        for plugin in registry.create_plugins(settings):
            manager.register(plugin)
        return manager

    def register(self, plugin: BasePlugin) -> None:
        self.plugins[plugin.name] = plugin

    def apply_overrides(self, disabled: Iterable[str]) -> None:
        for name in disabled:
            self.settings.setdefault(name, {})["enabled"] = False

    def enabled(self, name: str) -> bool:
        return bool(self.settings.get(name, {}).get("enabled", True))

    def plugins_for_kind(self, kind: str) -> list[BasePlugin]:
        plugins = [
            plugin
            for plugin in self.plugins.values()
            if plugin.kind == kind and self.enabled(plugin.name)
        ]
        plugins.sort(key=lambda plugin: int(self.settings.get(plugin.name, {}).get("order", default_order(plugin.kind))))
        return plugins

    def run_stage(self, kind: str, ctx: PluginContext) -> list[PluginResult]:
        results: list[PluginResult] = []
        for plugin in self.plugins_for_kind(kind):
            started_at = db.utc_now()
            started = time.perf_counter()
            try:
                result = plugin.run(ctx)
            except Exception as exc:
                logging.exception("Plugin %s failed", plugin.name)
                result = PluginResult(plugin.name, plugin.kind, status="failed", error=str(exc))
            duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
            db.log_plugin_run(
                ctx.conn,
                plugin_name=result.name,
                plugin_kind=result.kind,
                status=result.status,
                item_count=result.item_count,
                duration_ms=duration_ms,
                error_message=result.error,
                started_at=started_at,
                finished_at=db.utc_now(),
            )
            ctx.results.append(result)
            results.append(result)
        return results

    def sync_health_enabled(self, ctx: PluginContext) -> None:
        for plugin in self.plugins.values():
            db.set_plugin_health_enabled(ctx.conn, plugin.name, plugin.kind, self.enabled(plugin.name))
