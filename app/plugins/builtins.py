from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .. import db
from ..ccswitch import configure_from_ccswitch
from ..deadline_extractor import extract_deadlines
from ..dedup import dedupe_cross_source
from ..feedback_weights import apply_feedback_score, load_feedback_weights
from ..fetch_github import fetch_from_config, repo_to_item, sample_repositories
from ..fetch_rss import fetch_rss_from_config, rss_entry_to_item
from ..fetch_trending import fetch_trending
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
        GithubTrendingCollectorPlugin,
        WebpageCollectorPlugin,
        RssCollectorPlugin,
        FeedbackEnricherPlugin,
        DeadlineEnricherPlugin,
        CrossSourceDedupePlugin,
        LarkDigestEnricherPlugin,
        SummarizerPlugin,
        RendererPlugin,
        LarkSenderPlugin,
        MailSenderPlugin,
        WebhookSenderPlugin,
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
    return [item for item in items if effective_score(item) >= threshold and not item.get("filtered_by_feedback")]


def effective_score(item: dict[str, Any]) -> float:
    return float(item.get("_effective_score", item.get("_score", item.get("score", 0))) or 0)


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


class GithubTrendingCollectorPlugin(BasePlugin):
    name = "github_trending"
    kind = "collector"
    description = "Fetch GitHub Trending repositories"

    def run(self, ctx: PluginContext) -> PluginResult:
        trending_config = ((ctx.source_config.get("github") or {}).get("trending") or {})
        if not trending_config.get("enabled", False):
            return PluginResult(self.name, self.kind, status="skipped")
        languages = list(trending_config.get("languages") or ["any"])
        since = str(trending_config.get("since") or "daily")
        limit = int(trending_config.get("limit") or self.config.get("limit") or 10)
        repos: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for language in languages:
            try:
                repos.extend(fetch_trending(str(language), since=since)[:limit])
            except Exception as exc:
                errors.append({"source_name": f"github-trending:{language}", "url": "https://github.com/trending", "error": str(exc)})
        ranked = top_repos(repos, ctx.source_config, limit=limit)
        source_id = db.upsert_source(ctx.conn, "github-trending", "github_repo", trending_config)
        item_ids = ctx.list_state("item_ids")
        existing = ctx.list_state("ranked_repos")
        for repo in ranked:
            db.upsert_repo_snapshot(ctx.conn, repo, ctx.digest_date.isoformat())
            item_id = db.upsert_item(ctx.conn, repo_to_item(repo, source_id, repo["_score"]))
            repo["_item_id"] = item_id
            item_ids.append(item_id)
            existing.append(repo)
        if errors:
            ctx.list_state("source_errors").extend(errors)
        ctx.state["ranked_repos"] = sorted(existing, key=lambda item: effective_score(item), reverse=True)
        return PluginResult(self.name, self.kind, item_count=len(ranked), data={"errors": errors})


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


class FeedbackEnricherPlugin(BasePlugin):
    name = "feedback"
    kind = "enricher"
    description = "Apply user feedback as derived effective scores"

    def run(self, ctx: PluginContext) -> PluginResult:
        weights = load_feedback_weights(ctx.conn)
        count = 0
        for collection_name in ("ranked_repos", "web_items"):
            for item in ctx.state.get(collection_name, []) or []:
                base = effective_score(item)
                score, reasons = apply_feedback_score(base, item, weights)
                item["_effective_score"] = score
                if reasons:
                    item["_feedback_reasons"] = reasons
                count += 1
            ctx.state[collection_name] = sorted(ctx.state.get(collection_name, []), key=effective_score, reverse=True)
        return PluginResult(self.name, self.kind, item_count=count)


class DeadlineEnricherPlugin(BasePlugin):
    name = "deadline"
    kind = "enricher"
    description = "Extract deadline events from collected notices"

    def run(self, ctx: PluginContext) -> PluginResult:
        events: list[dict[str, Any]] = []
        for item in ctx.state.get("web_items", []) or []:
            candidates = extract_deadlines(
                str(item.get("title") or ""),
                str(item.get("content_snippet") or ""),
                str(item.get("content_full") or ""),
                source_url=str(item.get("url") or ""),
                item_id=item.get("_item_id"),
                today=ctx.digest_date,
            )
            for candidate in candidates:
                event = candidate.as_dict()
                event["id"] = db.upsert_deadline_event(ctx.conn, event)
                events.append(event)
        ctx.state["deadline_events"] = sorted(
            events,
            key=lambda item: (item.get("status") != "pending", item.get("deadline") or "", -float(item.get("confidence") or 0)),
        )
        return PluginResult(self.name, self.kind, item_count=len(events))


class CrossSourceDedupePlugin(BasePlugin):
    name = "cross_source_dedupe"
    kind = "enricher"
    description = "Remove near-duplicate web/RSS items across sources"

    def run(self, ctx: PluginContext) -> PluginResult:
        before = len(ctx.state.get("web_items", []) or [])
        threshold = float(self.config.get("threshold") or 0.6)
        ctx.state["web_items"] = dedupe_cross_source(list(ctx.state.get("web_items", []) or []), threshold=threshold)
        return PluginResult(self.name, self.kind, item_count=before - len(ctx.state["web_items"]))


class LarkDigestEnricherPlugin(BasePlugin):
    name = "lark_digest"
    kind = "enricher"
    description = "Prepare a compact Lark-specific digest field"

    def run(self, ctx: PluginContext) -> PluginResult:
        text = ctx.state.get("text_content")
        if text:
            ctx.state["lark_text_content"] = text
        return PluginResult(self.name, self.kind, item_count=1 if text else 0)


class SummarizerPlugin(BasePlugin):
    name = "summarizer"
    kind = "summarizer"
    description = "Build digest text from collected candidates"

    def run(self, ctx: PluginContext) -> PluginResult:
        text_content, mode = build_digest(
            ctx.state.get("ranked_repos", []),
            web_items=ctx.state.get("web_items", []),
            source_errors=ctx.state.get("source_errors", []),
            deadline_events=ctx.state.get("deadline_events", []),
        )
        ctx.state["text_content"] = text_content
        ctx.state["lark_text_content"] = text_content
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
            deadline_events=ctx.state.get("deadline_events", []),
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
            lark_text = ctx.state.get("lark_text_content") or ctx.state["text_content"]
            lark_item_ids = ctx.state.get("item_ids", [])
            if ctx.options.get("lark_only_important"):
                threshold = important_threshold()
                lark_repos = filter_important(ctx.state.get("ranked_repos", []), threshold)
                lark_web_items = filter_important(ctx.state.get("web_items", []), threshold)
                if ctx.options.get("incremental"):
                    lark_repos = filter_incremental_items(ctx, lark_repos)
                    lark_web_items = filter_incremental_items(ctx, lark_web_items)
                    if not lark_repos and not lark_web_items:
                        logging.info("Lark incremental important mode found no unnotified high-score items")
                        return PluginResult(self.name, self.kind, status="skipped")
                lark_text, lark_mode = build_digest(
                    lark_repos,
                    web_items=lark_web_items,
                    source_errors=ctx.state.get("source_errors", []),
                    deadline_events=ctx.state.get("deadline_events", []),
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


class WebhookSenderPlugin(BasePlugin):
    name = "webhook"
    kind = "sender"
    description = "Send digest to a generic webhook"

    def run(self, ctx: PluginContext) -> PluginResult:
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()
        if not webhook_url:
            return PluginResult(self.name, self.kind, status="skipped")
        payload = {
            "title": ctx.state.get("title") or ctx.state.get("subject"),
            "text": ctx.state.get("text_content", ""),
            "delivery_slot": ctx.state.get("delivery_slot"),
            "archive_path": str(ctx.state.get("archive_path") or ""),
        }
        response = requests.post(webhook_url, json=payload, timeout=int(os.getenv("WEBHOOK_TIMEOUT", "15")))
        if response.status_code >= 400:
            raise RuntimeError(f"Webhook HTTP {response.status_code}: {response.text[:200]}")
        return PluginResult(self.name, self.kind, item_count=1)


def filter_incremental_items(ctx: PluginContext, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = item_ids_from(items)
    meta = db.load_item_notification_meta(ctx.conn, ids)
    hours = float(os.getenv("DAILY_BRIEF_INCREMENTAL_WINDOW_HOURS", "4"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("_item_id")
        if item_id is None:
            continue
        row = meta.get(int(item_id))
        if not row or row.get("last_notified_slot"):
            continue
        first_seen = parse_datetime(row.get("first_seen_at") or row.get("fetched_at"))
        if first_seen and first_seen >= cutoff:
            result.append(item)
    return result


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
