from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import db
from .config import default_paths, load_yaml_config
from .knowledge import list_recent_items, list_saved_items, mark_item, search_items, tag_item
from .plugins.manager import load_plugin_settings
from .plugins.registry import set_plugin_enabled
from .runner import RunOptions, build_registry, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brief", description="Manage daily open-source brief")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the daily brief pipeline")
    add_run_args(run_parser)

    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)
    add_common_config_arg(plugin_sub.add_parser("list", help="List plugins"))
    add_common_config_arg(plugin_sub.add_parser("check", help="Validate plugin registry and config"))
    add_common_config_arg(plugin_sub.add_parser("status", help="Show plugin health"))
    enable_parser = add_common_config_arg(plugin_sub.add_parser("enable", help="Enable plugin"))
    enable_parser.add_argument("name")
    disable_parser = add_common_config_arg(plugin_sub.add_parser("disable", help="Disable plugin"))
    disable_parser.add_argument("name")

    config_parser = subparsers.add_parser("config", help="Show or validate configuration")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    add_common_config_arg(config_sub.add_parser("show", help="Show merged plugin config"))
    add_common_config_arg(config_sub.add_parser("validate", help="Validate plugin config"))

    kb_parser = subparsers.add_parser("kb", help="Search and manage the local knowledge base")
    kb_sub = kb_parser.add_subparsers(dest="kb_command", required=True)
    kb_search = kb_sub.add_parser("search", help="Search stored items")
    kb_search.add_argument("keyword")
    kb_search.add_argument("--limit", type=int, default=20)
    kb_recent = kb_sub.add_parser("recent", help="List recent items")
    kb_recent.add_argument("--limit", type=int, default=20)
    kb_mark = kb_sub.add_parser("mark", help="Mark item feedback")
    kb_mark.add_argument("item_id", type=int)
    kb_mark.add_argument("mark")
    kb_tag = kb_sub.add_parser("tag", help="Tag an item")
    kb_tag.add_argument("item_id", type=int)
    kb_tag.add_argument("tag")
    kb_saved = kb_sub.add_parser("saved", help="List saved items")
    kb_saved.add_argument("--limit", type=int, default=20)
    return parser


def add_common_config_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--plugins-config", default=None, help="Plugin config file, defaults to config/plugins.yml")
    return parser


def add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", dest="digest_date", default=date.today().isoformat())
    parser.add_argument("--config", default=None)
    parser.add_argument("--plugins-config", default=None, help="Plugin config file, defaults to config/plugins.yml")
    parser.add_argument("--skip-mail", action="store_true")
    parser.add_argument("--skip-lark", action="store_true")
    parser.add_argument("--force-send", action="store_true")
    parser.add_argument("--sample", action="store_true", help="Use bundled sample repositories and skip GitHub API")
    parser.add_argument("--skip-web", action="store_true", help="Skip configured public webpage sources")
    parser.add_argument("--skip-rss", action="store_true", help="Skip configured RSS/Atom sources")
    parser.add_argument("--archive-retention-days", type=int, default=None, help="Delete archive HTML files older than this many days")
    parser.add_argument("--collect-only", action="store_true", help="Fetch, rank, and store candidates without sending")
    parser.add_argument("--send-only", action="store_true", help="Build and deliver a digest from stored candidates")
    parser.add_argument("--delivery-slot", default=None, help="Delivery slot key, defaults to YYYY-MM-DD-HH")
    parser.add_argument("--lark-only-important", action="store_true", help="Send only high-score items to Lark")


def plugin_config_path(value: str | None) -> Path:
    paths = default_paths()
    return paths.root / value if value else paths.plugins


def plugin_context(args: argparse.Namespace) -> tuple[Any, dict[str, dict[str, Any]], Path]:
    paths = default_paths()
    config_path = plugin_config_path(getattr(args, "plugins_config", None))
    settings = load_plugin_settings(config_path)
    registry = build_registry(paths.root)
    return registry, settings, config_path


def print_plugin_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No plugins registered")
        return
    print(f"{'name':<14} {'kind':<10} {'enabled':<8} {'order':<5} {'version':<8} description")
    for row in rows:
        enabled = "yes" if row["enabled"] else "no"
        print(
            f"{row['name']:<14} {row['kind']:<10} {enabled:<8} "
            f"{row['order']:<5} {row['version']:<8} {row['description']}"
        )


def command_plugin(args: argparse.Namespace) -> int:
    registry, settings, config_path = plugin_context(args)
    if args.plugin_command == "list":
        print_plugin_rows(registry.list_plugins(settings))
        if registry.load_errors:
            print("\nload errors:")
            for error in registry.load_errors:
                print(f"- {error}")
        return 0
    if args.plugin_command == "check":
        issues = registry.validate(settings)
        if not issues:
            print("Plugin config OK")
            return 0
        for issue in issues:
            prefix = f"{issue.level.upper()}:"
            plugin = f" [{issue.plugin}]" if issue.plugin else ""
            print(f"{prefix}{plugin} {issue.message}")
        return 1 if any(issue.level == "error" for issue in issues) else 0
    if args.plugin_command == "enable":
        set_plugin_enabled(config_path, args.name, True)
        print(f"enabled {args.name}")
        return 0
    if args.plugin_command == "disable":
        set_plugin_enabled(config_path, args.name, False)
        print(f"disabled {args.name}")
        return 0
    if args.plugin_command == "status":
        paths = default_paths()
        with db.connect(paths.db) as conn:
            health = {item["plugin_name"]: item for item in db.load_plugin_health(conn)}
        rows = registry.list_plugins(settings)
        print(f"{'name':<14} {'kind':<10} {'enabled':<8} {'last':<10} {'items':<7} {'ms':<7} error")
        for row in rows:
            item = health.get(row["name"], {})
            enabled = "yes" if row["enabled"] else "no"
            status = item.get("last_status") or "never"
            count = item.get("last_item_count", "-")
            duration = item.get("last_duration_ms", "-")
            error = item.get("last_error") or ""
            print(f"{row['name']:<14} {row['kind']:<10} {enabled:<8} {status:<10} {count!s:<7} {duration!s:<7} {error}")
        return 0
    raise RuntimeError(f"unknown plugin command: {args.plugin_command}")


def command_config(args: argparse.Namespace) -> int:
    registry, settings, config_path = plugin_context(args)
    if args.config_command == "show":
        raw = load_yaml_config(config_path)
        print(yaml.safe_dump(raw or {"plugins": settings}, allow_unicode=True, sort_keys=False).strip())
        return 0
    if args.config_command == "validate":
        issues = registry.validate(settings)
        if not issues:
            print("Config OK")
            return 0
        for issue in issues:
            plugin = f" [{issue.plugin}]" if issue.plugin else ""
            print(f"{issue.level.upper()}:{plugin} {issue.message}")
        return 1 if any(issue.level == "error" for issue in issues) else 0
    raise RuntimeError(f"unknown config command: {args.config_command}")


def command_kb(args: argparse.Namespace) -> int:
    paths = default_paths()
    try:
        with db.connect(paths.db) as conn:
            if args.kb_command == "search":
                print_kb_items(search_items(conn, args.keyword, limit=args.limit))
                return 0
            if args.kb_command == "recent":
                print_kb_items(list_recent_items(conn, limit=args.limit))
                return 0
            if args.kb_command == "mark":
                feedback = mark_item(conn, args.item_id, args.mark, source="cli")
                print(
                    f"marked {feedback['item_id']} {feedback['feedback_type']}="
                    f"{'yes' if feedback['value'] else 'no'}"
                )
                return 0
            if args.kb_command == "tag":
                tag = tag_item(conn, args.item_id, args.tag, source="cli")
                print(f"tagged {tag['item_id']} {tag['tag']}")
                return 0
            if args.kb_command == "saved":
                print_kb_items(list_saved_items(conn, limit=args.limit))
                return 0
    except ValueError as exc:
        print(str(exc))
        return 2
    raise RuntimeError(f"unknown kb command: {args.kb_command}")


def format_kb_item(item: dict[str, Any]) -> str:
    score = float(item.get("score") or 0)
    seen_at = item.get("last_seen_at") or item.get("first_seen_at") or ""
    tags = ", ".join(item.get("tags") or [])
    marks = ", ".join(key for key, value in sorted((item.get("feedback") or {}).items()) if value)
    suffix = []
    if tags:
        suffix.append(f"tags={tags}")
    if marks:
        suffix.append(f"marks={marks}")
    meta = f" | {' | '.join(suffix)}" if suffix else ""
    return f"[{item['id']}] {item['title']} | {item['source_type']} | {score:.1f} | {seen_at}{meta}\n{item['url']}"


def print_kb_items(items: list[dict[str, Any]]) -> None:
    if not items:
        print("No items found.")
        return
    for item in items:
        print(format_kb_item(item))
        print()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run(RunOptions.from_namespace(args))
    if args.command == "plugin":
        return command_plugin(args)
    if args.command == "config":
        return command_config(args)
    if args.command == "kb":
        return command_kb(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
