from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from ..config import Paths


@dataclass
class PluginResult:
    name: str
    kind: str
    status: str = "success"
    item_count: int = 0
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginContext:
    conn: Connection
    paths: Paths
    source_config: dict[str, Any]
    digest_date: date
    options: dict[str, Any]
    state: dict[str, Any] = field(default_factory=dict)
    results: list[PluginResult] = field(default_factory=list)

    def list_state(self, key: str) -> list[Any]:
        value = self.state.setdefault(key, [])
        if not isinstance(value, list):
            raise TypeError(f"state[{key!r}] is not a list")
        return value


class BasePlugin:
    name = "base"
    kind = "base"
    version = "0.1.0"
    description = ""
    config_schema: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def run(self, ctx: PluginContext) -> PluginResult:
        raise NotImplementedError
