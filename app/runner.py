from __future__ import annotations

import logging
import os
from argparse import Namespace
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from . import db
from .config import default_paths, load_sources
from .lark_sender import lark_configured
from .mailer import smtp_configured
from .plugins.base import PluginContext
from .plugins.builtins import apply_model_override, builtin_registry, delivery_slot, load_stored_candidates
from .plugins.local_loader import load_local_plugins
from .plugins.manager import PluginManager, load_plugin_settings
from .plugins.registry import PluginRegistry


@dataclass
class RunOptions:
    digest_date: str
    config: str | None = None
    plugins_config: str | None = None
    skip_mail: bool = False
    skip_lark: bool = False
    force_send: bool = False
    sample: bool = False
    skip_web: bool = False
    skip_rss: bool = False
    archive_retention_days: int | None = None
    collect_only: bool = False
    send_only: bool = False
    delivery_slot: str | None = None
    lark_only_important: bool = False

    @classmethod
    def from_namespace(cls, args: Namespace) -> "RunOptions":
        return cls(**{field: getattr(args, field) for field in cls.__dataclass_fields__ if hasattr(args, field)})

    def as_dict(self) -> dict[str, Any]:
        return {
            "digest_date": self.digest_date,
            "config": self.config,
            "plugins_config": self.plugins_config,
            "skip_mail": self.skip_mail,
            "skip_lark": self.skip_lark,
            "force_send": self.force_send,
            "sample": self.sample,
            "skip_web": self.skip_web,
            "skip_rss": self.skip_rss,
            "archive_retention_days": self.archive_retention_days,
            "collect_only": self.collect_only,
            "send_only": self.send_only,
            "delivery_slot": self.delivery_slot,
            "lark_only_important": self.lark_only_important,
        }


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "daily.log", encoding="utf-8"),
        ],
    )


def disabled_plugins_from_options(options: RunOptions) -> list[str]:
    disabled: list[str] = []
    if options.skip_web:
        disabled.append("webpage")
    if options.skip_rss:
        disabled.append("rss")
    if options.skip_mail:
        disabled.append("mail")
    if options.skip_lark:
        disabled.append("lark")
    return disabled


def build_registry(root: Path) -> PluginRegistry:
    registry = builtin_registry()
    load_local_plugins(registry, root)
    return registry


def run(options: RunOptions) -> int:
    digest_date = date.fromisoformat(options.digest_date)
    paths = default_paths()
    setup_logging(paths.log_dir)

    config_path = paths.root / options.config if options.config else paths.config
    source_config = load_sources(config_path, today=digest_date)
    plugins_path = paths.root / options.plugins_config if options.plugins_config else paths.plugins
    plugin_settings = load_plugin_settings(plugins_path)
    registry = build_registry(paths.root)
    manager = PluginManager.from_registry(registry, plugin_settings)
    disabled_plugins = disabled_plugins_from_options(options)
    manager.apply_overrides(disabled_plugins)
    for plugin_name in disabled_plugins:
        logging.info("Plugin %s disabled by CLI flag", plugin_name)

    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.archive_dir.mkdir(parents=True, exist_ok=True)

    with db.connect(paths.db) as conn:
        if options.collect_only and options.send_only:
            raise RuntimeError("--collect-only and --send-only cannot be used together")

        options_dict = options.as_dict()
        slot = delivery_slot(options_dict)
        subject_prefix = os.getenv("MAIL_SUBJECT_PREFIX", "开源日报")
        ctx = PluginContext(
            conn=conn,
            paths=paths,
            source_config=source_config,
            digest_date=digest_date,
            options=options_dict,
            state={
                "item_ids": [],
                "web_items": [],
                "source_errors": [],
                "delivery_slot": slot,
                "subject": f"{subject_prefix} {slot}",
            },
        )
        manager.sync_health_enabled(ctx)

        if not options.send_only:
            apply_model_override("DAILY_BRIEF_COLLECT_MODEL")
            manager.run_stage("collector", ctx)
            ctx.state["web_items"] = sorted(
                ctx.state.get("web_items", []),
                key=lambda item: (item.get("_score", 0), item.get("published_at") or ""),
                reverse=True,
            )
            if options.collect_only:
                logging.info("Collection complete; stored %d ranked candidates", len(ctx.state.get("ranked_repos", [])))
                return 0
        else:
            load_stored_candidates(ctx)

        ctx.state["source_health"] = db.load_source_health(conn)
        manager.run_stage("provider", ctx)
        apply_model_override("DAILY_BRIEF_SEND_MODEL")

        mail_needed = manager.enabled("mail") and smtp_configured()
        lark_needed = manager.enabled("lark") and lark_configured()
        if not options.force_send and mail_needed and not lark_needed and db.mail_already_sent(conn, slot):
            logging.info("Mail already sent for slot %s; use --force-send to resend", slot)
            return 0

        manager.run_stage("summarizer", ctx)
        manager.run_stage("renderer", ctx)
        sender_results = manager.run_stage("sender", ctx)
        if any(result.status == "failed" and result.name == "mail" for result in sender_results):
            return 2
    return 0
