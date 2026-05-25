from __future__ import annotations

import importlib.util
from pathlib import Path

from .registry import PluginRegistry


def load_local_plugins(registry: PluginRegistry, root: Path) -> None:
    local_dir = root / "plugins" / "local"
    if not local_dir.exists():
        return
    for path in sorted(local_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"daily_open_source_brief_local_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if not spec or not spec.loader:
                raise RuntimeError("cannot create import spec")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise RuntimeError("missing callable register(registry)")
            register(registry)
        except Exception as exc:
            registry.load_errors.append(f"{path}: {type(exc).__name__}: {exc}")
