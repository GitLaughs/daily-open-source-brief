from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Type

import yaml

from ..config import load_yaml_config
from .base import BasePlugin


VALID_KINDS = {"provider", "collector", "summarizer", "renderer", "sender"}


@dataclass
class RegistryIssue:
    level: str
    message: str
    plugin: str | None = None


@dataclass
class PluginRegistry:
    plugin_types: dict[str, Type[BasePlugin]] = field(default_factory=dict)
    load_errors: list[str] = field(default_factory=list)

    def register(self, plugin_type: Type[BasePlugin]) -> None:
        name = getattr(plugin_type, "name", "")
        if not name or name == "base":
            raise ValueError("plugin class must define a unique name")
        if name in self.plugin_types:
            raise ValueError(f"duplicate plugin name: {name}")
        self.plugin_types[name] = plugin_type

    def create_plugins(self, settings: dict[str, dict[str, Any]]) -> list[BasePlugin]:
        return [plugin_type(settings.get(name, {})) for name, plugin_type in self.plugin_types.items()]

    def list_plugins(self, settings: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name, plugin_type in self.plugin_types.items():
            config = settings.get(name, {})
            rows.append(
                {
                    "name": name,
                    "kind": getattr(plugin_type, "kind", ""),
                    "version": getattr(plugin_type, "version", "0.1.0"),
                    "description": getattr(plugin_type, "description", ""),
                    "enabled": bool(config.get("enabled", True)),
                    "order": int(config.get("order", default_order(getattr(plugin_type, "kind", "")))),
                    "source": "registered",
                }
            )
        rows.sort(key=lambda item: (item["order"], item["kind"], item["name"]))
        return rows

    def validate(self, settings: dict[str, dict[str, Any]]) -> list[RegistryIssue]:
        issues: list[RegistryIssue] = []
        for error in self.load_errors:
            issues.append(RegistryIssue("error", error))
        for name, plugin_type in self.plugin_types.items():
            kind = getattr(plugin_type, "kind", "")
            if kind not in VALID_KINDS:
                issues.append(RegistryIssue("error", f"invalid plugin kind: {kind}", name))
        for name, config in settings.items():
            if name not in self.plugin_types:
                issues.append(RegistryIssue("warning", "configured plugin is not registered", name))
            if not isinstance(config, dict):
                issues.append(RegistryIssue("error", "plugin config must be a mapping", name))
                continue
            if "enabled" in config and not isinstance(config["enabled"], bool):
                issues.append(RegistryIssue("error", "enabled must be true or false", name))
            kind = config.get("kind")
            if kind is not None and str(kind) not in VALID_KINDS:
                issues.append(RegistryIssue("error", f"invalid configured kind: {kind}", name))
            if "order" in config:
                try:
                    int(config["order"])
                except (TypeError, ValueError):
                    issues.append(RegistryIssue("error", "order must be an integer", name))
        return issues


def default_order(kind: str) -> int:
    return {
        "provider": 10,
        "collector": 30,
        "summarizer": 50,
        "renderer": 70,
        "sender": 90,
    }.get(kind, 100)


def load_raw_plugin_config(path: Path) -> dict[str, Any]:
    data = load_yaml_config(path)
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        data["plugins"] = {}
    return data


def write_plugin_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def set_plugin_enabled(path: Path, name: str, enabled: bool) -> None:
    data = load_raw_plugin_config(path)
    plugins = data.setdefault("plugins", {})
    config = plugins.setdefault(name, {})
    if not isinstance(config, dict):
        config = {}
        plugins[name] = config
    config["enabled"] = enabled
    write_plugin_config(path, data)
