from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass(frozen=True)
class Paths:
    root: Path
    config: Path
    plugins: Path
    data_dir: Path
    db: Path
    archive_dir: Path
    log_dir: Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_paths(root: Optional[Path] = None) -> Paths:
    root = root or project_root()
    return Paths(
        root=root,
        config=root / "config" / "sources.yml",
        plugins=root / "config" / "plugins.yml",
        data_dir=root / "data",
        db=root / "data" / "brief.sqlite",
        archive_dir=root / "public" / "archive",
        log_dir=root / "logs",
    )


def load_sources(path: Path, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    pushed_after = today - timedelta(days=180)
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    for query in config.get("github", {}).get("queries", []):
        if "q" in query:
            query["q"] = str(query["q"]).format(pushed_after=pushed_after.isoformat())
    return config


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
