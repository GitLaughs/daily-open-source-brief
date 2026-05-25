from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from .. import db
from ..ccswitch import configure_from_ccswitch
from ..fetch_github import fetch_from_config, repo_to_item, sample_repositories
from ..fetch_rss import fetch_rss_from_config, rss_entry_to_item
from ..fetch_webpage import fetch_webpages_from_config, web_entry_to_item
from ..lark_sender import digest_markdown, lark_configured, lark_receive_id, send_lark_message
from ..mailer import send_mail, smtp_configured
from ..rank import top_repos
from ..render import prune_archives, render_email, write_archive
from ..summarize import build_digest
from .base import BasePlugin, PluginContext, PluginResult
from .manager import PluginManager
from .registry import PluginRegistry


def builtin_registry() -> PluginRegistry:
    registry = PluginRegistry()
    for plugin_type in [
        CcSwitchPlugin,
        GithubCollectorPlugin,
        WebpageCollectorPlugin,
        RssCollectorPlugin,
        SummarizerPlugin,
        RendererPlugin,
        LarkSenderPlugin,
        MailSenderPlugin,
    ]:
        registry.register(plugin_type)
    return registry


def builtin_manager(settings: dict[str, dict[str, Any]]) -> PluginManager:
    return PluginManager.from_registry(builtin_registry(), settings)


def apply_model_override(env_name: str) -> None:
    model = os.getenv(env_name, "").strip()
    if model:
        os.environ["OPENAI_MODEL"] = model


def important_threshold() -> float:
    value = os.getenv("DAILY_BRIEF_IMPORTANT_SCORE", "").strip()
    if not value:
        return 80.0
    try:
        return float(value)
    except ValueError:
        logging.warning("Invalid DAILY_BRIEF_IMPORTANT_SCORE=%r; using 80", value)
        return 80.0


def filter_important(items: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    return [item for item in items if float(item.get("_score") or item.get("score") or 0) >= threshold]


def item_ids_from(items: list[dict[str, Any]]) -> list[int]:
    return [int(item["_item_id"]) for item in items if item.get("_item_id") is not None]


class CcSwitchPlugin(BasePlugin):
    name = "ccswitch"
    kind = "provider"
    description = "Select OpenAI-compatible LLM provider from cc-switch"

    def run(self, ctx: PluginContext) -> PluginResult:
        provider = configure_from_ccswitch()
        if provider:
            ctx.state["ccswitch_provider"] = provider
            logging.info(
                "Configured LLM from cc-switch provider=%s model=%s remaining=%s",
                provider["name"],
                os.getenv("OPENAI_MODEL") or provider["model"],
                provider.get("remaining"),
            )
        return PluginResult(self.name, self.kind, item_count=1 if provider else 0)


class GithubCollectorPlugin(BasePlugin):
    name = "github"
    kind = "collector"
    description = "Fetch and rank GitHub repositories"

    def run(self, ctx: PluginContext) -> PluginResult:
        if ctx.options.get("sample"):
            repos = sample_repositories()
            logging.info("Loaded %d sample repositories", len(repos))
        else:
            repos = fetch_from_config(ctx.source_config)
            logging.info("Fetched %d repositories from GitHub", len(repos))

        ranked = top_repos(repos, ctx.source_config, limit=int(self.config.get("limit", 40)))
        source_id = db.upsert_source(ctx.conn, "github-search", "github_repo", ctx.source_config.get("github", {}))
        item_ids = ctx.list_state("item_ids")
        for repo in ranked:
            db.upsert_repo_snapshot(ctx.conn, repo, ctx.digest_date.isoformat())
            item_id = db.upsert_item(ctx.conn, repo_to_item(repo, source_id, repo["_score"]))
            repo["_item_id"] = item_id
            item_ids.append(item_id)
        ctx.state["ranked_repos"] = ranked
        return PluginResult(self.name, self.kind, item_count=len(ranked))


class WebpageCollectorPlugin(BasePlugin):
    name = "webpage"
    kind = "collector"
    description = "Fetch configured public webpage sources"

    def run(self, ctx: PluginContext) -> PluginResult:
        web_items, web_errors, web_runs = fetch_webpages_from_config(ctx.source_config, today=ctx.digest_date)
        db.log_source_runs(ctx.conn, web_runs)
        logging.info("Fetched %d public webpage items (%d source errors)", len(web_items), len(web_errors))
        item_ids = ctx.list_state("item_ids")
        for item in web_items:
            source_config = item.get("_source_config") or {}
            source_id = db.upsert_source(
                ctx.conn,
                str(source_config.get("name") or item.get("source_name") or "webpage"),
                str(item.get("source_type") or "school_notice"),
                {
                    "url": source_config.get("url") or item.get("url"),
                    "title": source_config.get("title") or item.get("source_title"),
                    "category": source_config.get("category") or item.get("category"),
                },
            )
            item_id = db.upsert_item(ctx.conn, web_entry_to_item(item, source_id))
            item["_item_id"] = item_id
            item_ids.append(item_id)
        ctx.list_state("web_items").extend(web_items)
        ctx.list_state("source_errors").extend(web_errors)
        return PluginResult(self.name, self.kind, item_count=len(web_items), data={"errors": web_errors})


class RssCollectorPlugin(BasePlugin):
    name = "rss"
    kind = "collector"
    description = "Fetch configured RSS and Atom feeds"

    def run(self, ctx: PluginContext) -> PluginResult:
        rss_items, rss_errors, rss_runs = fetch_rss_from_config(ctx.source_config, today=ctx.digest_date)
        db.log_source_runs(ctx.conn, rss_runs)
        logging.info("Fetched %d RSS items (%d source errors)", len(rss_items), len(rss_errors))
        item_ids = ctx.list_state("item_ids")
        for item in rss_items:
            source_config = item.get("_source_config") or {}
            source_id = db.upsert_source(
                ctx.conn,
                str(source_config.get("name") or item.get("source_name") or "rss"),
                str(item.get("source_type") or "rss_entry"),
                {
                    "url": source_config.get("url") or item.get("url"),
                    "title": source_config.get("title") or item.get("source_title"),
                    "category": source_config.get("category") or item.get("category"),
                },
            )
            item_id = db.upsert_item(ctx.conn, rss_entry_to_item(item, source_id))
            item["_item_id"] = item_id
            item_ids.append(item_id)
        ctx.list_state("web_items").extend(rss_items)
        ctx.list_state("source_errors").extend(rss_errors)
        return PluginResult(self.name, self.kind, item_count=len(rss_items), data={"errors": rss_errors})


class SummarizerPlugin(BasePlugin):
    name = "summarizer"
    kind = "summarizer"
    description = "Build digest text from collected candidates"

    def run(self, ctx: PluginContext) -> PluginResult:
        text_content, mode = build_digest(
            ctx.state.get("ranked_repos", []),
            web_items=ctx.state.get("web_items", []),
            source_errors=ctx.state.get("source_errors", []),
        )
        ctx.state["text_content"] = text_content
        ctx.state["digest_mode"] = mode
        return PluginResult(self.name, self.kind, data={"mode": mode})


class RendererPlugin(BasePlugin):
    name = "renderer"
    kind = "renderer"
    description = "Render HTML archive and persist digest"

    def run(self, ctx: PluginContext) -> PluginResult:
        digest_date = ctx.digest_date
        title = f"开源日报 {digest_date.isoformat()}"
        delivery_slot = ctx.state["delivery_slot"]
        html_content = render_email(
            digest_date,
            ctx.state["text_content"],
            ctx.state.get("ranked_repos", []),
            ctx.state["digest_mode"],
            web_items=ctx.state.get("web_items", []),
            source_errors=ctx.state.get("source_errors", []),
            source_health=ctx.state.get("source_health", []),
        )
        digest_id = db.save_digest(
            ctx.conn,
            delivery_slot,
            title,
            ctx.state["text_content"],
            html_content,
            ctx.state.get("item_ids", []),
        )
        archive_path = write_archive(ctx.paths.archive_dir, digest_date, html_content)
        logging.info("Wrote archive: %s", archive_path)
        retention_days = ctx.options.get("archive_retention_days")
        if retention_days is None:
            retention_value = os.getenv("DAILY_BRIEF_ARCHIVE_RETENTION_DAYS", "").strip()
            retention_days = int(retention_value) if retention_value else 0
        if retention_days > 0:
            deleted_archives = prune_archives(ctx.paths.archive_dir, today=digest_date, retention_days=retention_days)
            logging.info("Pruned %d archive files older than %d days", len(deleted_archives), retention_days)
        ctx.state.update(
            {
                "title": title,
                "html_content": html_content,
                "digest_id": digest_id,
                "archive_path": archive_path,
            }
        )
        return PluginResult(self.name, self.kind, item_count=1, data={"archive_path": str(archive_path)})


class LarkSenderPlugin(BasePlugin):
    name = "lark"
    kind = "sender"
    description = "Send digest through lark-cli"

    def run(self, ctx: PluginContext) -> PluginResult:
        if not lark_configured():
            logging.info("Lark not configured")
            return PluginResult(self.name, self.kind, status="skipped")
        delivery_slot = ctx.state["delivery_slot"]
        receive_id = lark_receive_id()
        subject = ctx.state["subject"]
        if not ctx.options.get("force_send") and db.lark_already_sent(ctx.conn, receive_id, delivery_slot):
            logging.info("Lark already sent for slot %s", delivery_slot)
            return PluginResult(self.name, self.kind, status="skipped")
        try:
            lark_title = ctx.state["title"]
            lark_text = ctx.state["text_content"]
            lark_item_ids = ctx.state.get("item_ids", [])
            if ctx.options.get("lark_only_important"):
                threshold = important_threshold()
                lark_repos = filter_important(ctx.state.get("ranked_repos", []), threshold)
                lark_web_items = filter_important(ctx.state.get("web_items", []), threshold)
                lark_text, lark_mode = build_digest(
                    lark_repos,
                    web_items=lark_web_items,
                    source_errors=ctx.state.get("source_errors", []),
                )
                lark_title = f"{ctx.state['title']} 高优先级"
                lark_item_ids = item_ids_from(lark_repos) + item_ids_from(lark_web_items)
                logging.info(
                    "Lark important mode selected %d repos and %d web/RSS items threshold=%.1f mode=%s",
                    len(lark_repos),
                    len(lark_web_items),
                    threshold,
                    lark_mode,
                )
            lark_data = send_lark_message(
                digest_markdown(lark_title, lark_text, ctx.state["archive_path"]),
                delivery_slot,
            )
            db.log_lark(
                ctx.conn,
                ctx.state["digest_id"],
                receive_id,
                subject,
                delivery_slot,
                "sent",
                message_id=lark_data.get("message_id"),
            )
            notified_count = db.mark_items_notified(ctx.conn, lark_item_ids, delivery_slot)
            logging.info("Lark sent message_id=%s", lark_data.get("message_id"))
            logging.info("Marked %d items notified for slot %s", notified_count, delivery_slot)
            return PluginResult(self.name, self.kind, item_count=1, data={"message_id": lark_data.get("message_id")})
        except Exception as exc:
            db.log_lark(ctx.conn, ctx.state["digest_id"], receive_id, subject, delivery_slot, "failed", error_message=str(exc))
            logging.exception("Lark send failed")
            ctx.list_state("source_errors").append({"source_name": "lark", "url": "", "error": str(exc)})
            return PluginResult(self.name, self.kind, status="failed", error=str(exc))


class MailSenderPlugin(BasePlugin):
    name = "mail"
    kind = "sender"
    description = "Send digest through SMTP"

    def run(self, ctx: PluginContext) -> PluginResult:
        subject = ctx.state["subject"]
        if not smtp_configured():
            db.log_mail(ctx.conn, ctx.state["digest_id"], os.getenv("MAIL_TO"), subject, "not_configured", "SMTP env missing")
            logging.warning("SMTP env missing; digest saved without sending")
            return PluginResult(self.name, self.kind, status="skipped")
        try:
            mail_to = send_mail(subject, ctx.state["text_content"], ctx.state["html_content"])
        except Exception as exc:
            db.log_mail(ctx.conn, ctx.state["digest_id"], os.getenv("MAIL_TO"), subject, "failed", str(exc))
            logging.exception("Mail send failed")
            return PluginResult(self.name, self.kind, status="failed", error=str(exc))
        db.log_mail(ctx.conn, ctx.state["digest_id"], mail_to, subject, "sent")
        logging.info("Mail sent to %s", mail_to)
        return PluginResult(self.name, self.kind, item_count=1, data={"mail_to": mail_to})


def load_stored_candidates(ctx: PluginContext) -> None:
    ranked, item_ids = db.load_recent_repos(ctx.conn, limit=80)
    ranked = top_repos(ranked, ctx.source_config, limit=20)
    repo_item_ids = item_ids[: len(ranked)]
    web_items, web_item_ids = db.load_recent_web_items(ctx.conn, limit=80)
    web_items = sorted(web_items, key=lambda item: (item.get("_score", 0), item.get("published_at") or ""), reverse=True)[:20]
    ctx.state["ranked_repos"] = ranked
    ctx.state["web_items"] = web_items
    ctx.state["item_ids"] = repo_item_ids + web_item_ids[: len(web_items)]
    ctx.state["source_errors"] = []
    logging.info("Loaded %d stored repo candidates and %d webpage candidates for digest", len(ranked), len(web_items))


def delivery_slot(options: dict[str, Any]) -> str:
    return options.get("delivery_slot") or os.getenv("DAILY_BRIEF_DELIVERY_SLOT") or datetime.now().strftime("%Y-%m-%d-%H")
