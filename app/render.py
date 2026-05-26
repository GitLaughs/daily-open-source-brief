from __future__ import annotations

import html
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def linkify(escaped_text: str) -> str:
    return re.sub(
        r"(https?://[^\s<]+)",
        lambda match: f'<a href="{html.escape(match.group(1), quote=True)}">{match.group(1)}</a>',
        escaped_text,
    )


def markdownish_to_html(text: str) -> str:
    lines: list[str] = []
    in_list = False
    li_open = False

    def close_li() -> None:
        nonlocal li_open
        if li_open:
            lines.append("</li>")
            li_open = False

    def close_list() -> None:
        nonlocal in_list
        close_li()
        if in_list:
            lines.append("</ul>")
            in_list = False

    for raw in text.splitlines():
        stripped = raw.strip()
        line = linkify(html.escape(stripped))
        if line.startswith("# "):
            close_list()
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            close_list()
            lines.append(f"<h2>{line[3:]}</h2>")
        elif stripped.startswith("- "):
            if not in_list:
                lines.append('<ul class="digest-list">')
                in_list = True
            close_li()
            lines.append(f"<li>{linkify(html.escape(stripped[2:]))}")
            li_open = True
        elif raw.startswith(("  ", "\t")) and li_open:
            lines.append(f"<p>{line}</p>")
        elif stripped == "":
            close_list()
        else:
            close_list()
            lines.append(f"<p>{line}</p>")
    close_list()
    return "\n".join(lines)


def render_email(
    digest_date: date,
    text_content: str,
    repos: list[dict[str, Any]],
    mode: str,
    web_items: list[dict[str, Any]] | None = None,
    source_errors: list[dict[str, str]] | None = None,
    source_health: list[dict[str, Any]] | None = None,
    deadline_events: list[dict[str, Any]] | None = None,
) -> str:
    web_items = web_items or []
    source_errors = source_errors or []
    source_health = source_health or []
    deadline_events = deadline_events or []
    rows: list[str] = []
    for repo in repos[:20]:
        rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(repo['html_url'])}\">{html.escape(repo['full_name'])}</a></td>"
            f"<td>{int(repo.get('stargazers_count') or 0):,}</td>"
            f"<td>{html.escape(repo.get('language') or '')}</td>"
            f"<td>{html.escape(str(repo.get('_effective_score', repo.get('_score', ''))))}</td>"
            "</tr>"
        )
    table = "\n".join(rows) if rows else "<tr><td colspan=\"4\">今日无高价值更新</td></tr>"
    body = markdownish_to_html(text_content)
    school_cards = render_web_cards(web_items[:8])
    repo_cards = render_repo_cards(repos[:6])
    deadlines = render_deadline_events(deadline_events)
    health = render_source_health(source_errors, source_health)
    metrics = render_metrics(repos, web_items, mode)
    template_path = Path(__file__).resolve().parents[1] / "templates"
    if template_path.exists():
        env = Environment(loader=FileSystemLoader(template_path), autoescape=select_autoescape(["html", "xml"]))
        template = env.get_template("email.html")
        return template.render(
            digest_date=digest_date,
            mode=mode,
            metrics=metrics,
            body=body,
            deadlines=deadlines,
            school_cards=school_cards,
            repo_cards=repo_cards,
            health=health,
            table=table,
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>开源日报 {digest_date.isoformat()}</title>
  <style>
    :root {{
      --color-primary: #0f766e;
      --color-secondary: #2563eb;
      --color-neutral-50: #f8f9fa;
      --color-neutral-100: #f3f4f6;
      --color-neutral-200: #e5e7eb;
      --color-neutral-300: #d1d5db;
      --color-neutral-500: #6b7280;
      --color-neutral-600: #4b5563;
      --color-neutral-900: #111827;
      --color-success: #15803d;
      --color-warning: #b45309;
      --color-error: #b91c1c;
      --text-xs: 12px;
      --text-sm: 14px;
      --text-base: 16px;
      --text-lg: 20px;
      --text-xl: 24px;
      --text-2xl: 32px;
      --space-1: 4px;
      --space-2: 8px;
      --space-3: 12px;
      --space-4: 16px;
      --space-6: 24px;
      --space-8: 32px;
      --space-12: 48px;
      --space-16: 64px;
      --radius-card: 8px;
    }}
    body {{
      margin: 0;
      background: var(--color-neutral-100);
      color: var(--color-neutral-900);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      font-size: var(--text-base);
      line-height: 1.5;
    }}
    main {{ max-width: 920px; margin: 0 auto; padding: var(--space-8) var(--space-4) var(--space-12); background: #ffffff; }}
    header {{ border-bottom: 1px solid var(--color-neutral-200); padding-bottom: var(--space-6); margin-bottom: var(--space-6); }}
    h1 {{ font-size: var(--text-2xl); line-height: 1.25; margin: 0 0 var(--space-2); font-weight: 600; }}
    h2 {{ font-size: var(--text-lg); line-height: 1.25; margin: var(--space-8) 0 var(--space-4); font-weight: 600; }}
    h3 {{ font-size: var(--text-base); line-height: 1.25; margin: 0 0 var(--space-2); font-weight: 600; }}
    p {{ margin: 0 0 var(--space-3); }}
    a {{ color: var(--color-secondary); text-decoration: none; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: var(--space-4); font-size: var(--text-sm); }}
    th, td {{ border-bottom: 1px solid var(--color-neutral-200); padding: var(--space-3) var(--space-2); text-align: left; vertical-align: top; }}
    th {{ color: var(--color-neutral-600); font-weight: 600; background: var(--color-neutral-50); }}
    .meta {{ color: var(--color-neutral-500); font-size: var(--text-sm); }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); margin-top: var(--space-6); }}
    .metric {{ border: 1px solid var(--color-neutral-200); border-radius: var(--radius-card); padding: var(--space-4); background: #ffffff; }}
    .metric span {{ display: block; color: var(--color-neutral-500); font-size: var(--text-xs); }}
    .metric strong {{ display: block; margin-top: var(--space-1); font-size: var(--text-xl); line-height: 1.25; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-3); }}
    .item-card {{ border: 1px solid var(--color-neutral-200); border-radius: var(--radius-card); padding: var(--space-4); background: #ffffff; }}
    .item-card p {{ color: var(--color-neutral-600); font-size: var(--text-sm); }}
    .tagline {{ display: flex; gap: var(--space-2); flex-wrap: wrap; color: var(--color-neutral-500); font-size: var(--text-xs); margin-bottom: var(--space-2); }}
    .tag {{ border: 1px solid var(--color-neutral-200); border-radius: 6px; padding: var(--space-1) var(--space-2); background: var(--color-neutral-50); }}
    .digest {{ border: 1px solid var(--color-neutral-200); border-radius: var(--radius-card); padding: var(--space-6); background: var(--color-neutral-50); }}
    .digest h1 {{ font-size: var(--text-xl); }}
    .digest h2 {{ font-size: var(--text-base); margin-top: var(--space-6); border-bottom: 1px solid var(--color-neutral-200); padding-bottom: var(--space-2); }}
    .digest-list {{ margin: 0; padding-left: var(--space-6); }}
    .digest-list li {{ margin: var(--space-3) 0; }}
    .digest-list p {{ color: var(--color-neutral-600); font-size: var(--text-sm); margin: var(--space-1) 0 0; }}
    .health {{ color: var(--color-warning); font-size: var(--text-sm); }}
    @media (max-width: 680px) {{
      main {{ padding: var(--space-6) var(--space-3) var(--space-8); }}
      .metrics, .grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: var(--text-xl); }}
      table {{ font-size: var(--text-xs); }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="meta">生成日期：{digest_date.isoformat()} · 摘要模式：{html.escape(mode)}</div>
    <h1>个人技术与产业日报</h1>
    {metrics}
  </header>
  <section>
    <h2>今日简报</h2>
    <div class="digest">{body}</div>
  </section>
  {deadlines}
  <section>
    <h2>网页与 RSS 情报源</h2>
    {school_cards}
  </section>
  <section>
    <h2>开源项目速览</h2>
    {repo_cards}
  </section>
  {health}
  <h2>候选仓库快照</h2>
  <table>
    <thead><tr><th>项目</th><th>Stars</th><th>语言</th><th>评分</th></tr></thead>
    <tbody>{table}</tbody>
  </table>
</main>
</body>
</html>"""


def write_archive(archive_dir: Path, digest_date: date, html_content: str) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{digest_date.isoformat()}.html"
    path.write_text(html_content, encoding="utf-8")
    return path


def prune_archives(archive_dir: Path, *, today: date, retention_days: int) -> list[Path]:
    if retention_days <= 0 or not archive_dir.exists():
        return []
    cutoff = today - timedelta(days=retention_days)
    deleted: list[Path] = []
    for path in archive_dir.glob("*.html"):
        try:
            archive_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if archive_date >= cutoff:
            continue
        path.unlink()
        deleted.append(path)
    return deleted


def render_metrics(repos: list[dict[str, Any]], web_items: list[dict[str, Any]], mode: str) -> str:
    top_repo_stars = max((int(repo.get("stargazers_count") or 0) for repo in repos), default=0)
    return (
        '<div class="metrics">'
        f'<div class="metric"><span>网页/RSS 条目</span><strong>{len(web_items)}</strong></div>'
        f'<div class="metric"><span>开源候选项目</span><strong>{len(repos)}</strong></div>'
        f'<div class="metric"><span>最高 Stars</span><strong>{top_repo_stars:,}</strong></div>'
        f'<div class="metric"><span>输出模式</span><strong>{html.escape(mode.split(":", 1)[0])}</strong></div>'
        "</div>"
    )


def render_web_cards(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="meta">今日未抓到网页或 RSS 条目，或配置中未启用相关来源。</p>'
    cards = []
    for item in items:
        source = item.get("source_title") or item.get("source_name") or "官网"
        published = item.get("published_at") or "日期未知"
        snippet = item.get("content_snippet") or ""
        cards.append(
            '<article class="item-card">'
            f'<div class="tagline"><span class="tag">{html.escape(str(source))}</span><span>{html.escape(str(published))}</span></div>'
            f'<h3><a href="{html.escape(str(item.get("url") or ""), quote=True)}">{html.escape(str(item.get("title") or "未命名"))}</a></h3>'
            f"<p>{html.escape(str(snippet))}</p>"
            "</article>"
        )
    return '<div class="grid">' + "\n".join(cards) + "</div>"


def render_deadline_events(events: list[dict[str, Any]]) -> str:
    active = [event for event in events if event.get("status") != "expired"]
    if not active:
        return ""
    rows = []
    for event in active[:8]:
        rows.append(
            '<article class="item-card">'
            f'<div class="tagline"><span class="tag">{html.escape(str(event.get("event_type") or "事项"))}</span>'
            f'<span>{html.escape(str(event.get("deadline") or ""))}</span></div>'
            f'<h3><a href="{html.escape(str(event.get("source_url") or ""), quote=True)}">{html.escape(str(event.get("title") or "未命名"))}</a></h3>'
            f'<p>置信度 {float(event.get("confidence") or 0):.2f}</p>'
            "</article>"
        )
    return '<section><h2>截止事项</h2><div class="grid">' + "\n".join(rows) + "</div></section>"


def render_repo_cards(repos: list[dict[str, Any]]) -> str:
    if not repos:
        return '<p class="meta">今日未抓到开源项目候选。</p>'
    cards = []
    for repo in repos:
        license_obj = repo.get("license") or {}
        license_name = license_obj.get("spdx_id") if isinstance(license_obj, dict) else ""
        meta = [
            f"{int(repo.get('stargazers_count') or 0):,} stars",
            str(repo.get("language") or "Unknown"),
            str(license_name or "Unknown"),
        ]
        cards.append(
            '<article class="item-card">'
            f'<div class="tagline"><span class="tag">{html.escape(str(repo.get("_source_query") or "GitHub"))}</span><span>{html.escape(" · ".join(meta))}</span></div>'
            f'<h3><a href="{html.escape(str(repo.get("html_url") or ""), quote=True)}">{html.escape(str(repo.get("full_name") or "repo"))}</a></h3>'
            f'<p>{html.escape(str(repo.get("description") or "暂无简介"))}</p>'
            "</article>"
        )
    return '<div class="grid">' + "\n".join(cards) + "</div>"


def render_source_health(source_errors: list[dict[str, str]], source_health: list[dict[str, Any]]) -> str:
    if not source_errors and not source_health:
        return ""
    error_items = "".join(
        f"<li>{html.escape(error.get('source_name', 'source'))}: {html.escape(error.get('error', 'unknown'))}</li>"
        for error in source_errors[:5]
    )
    health_rows = []
    for item in source_health[:10]:
        status = str(item.get("last_status") or "unknown")
        label = "正常" if status == "success" else "异常"
        detail = f"{label} · {int(item.get('last_item_count') or 0)} 条 · {int(item.get('last_duration_ms') or 0)} ms"
        if item.get("last_error"):
            detail += " · " + str(item["last_error"])[:120]
        health_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('source_name') or 'source'))}</td>"
            f"<td>{html.escape(str(item.get('source_type') or ''))}</td>"
            f"<td>{html.escape(detail)}</td>"
            f"<td>{html.escape(str(item.get('updated_at') or ''))}</td>"
            "</tr>"
        )
    errors = f"<ul>{error_items}</ul>" if error_items else ""
    table = ""
    if health_rows:
        table = (
            "<table><thead><tr><th>来源</th><th>类型</th><th>最近状态</th><th>更新时间</th></tr></thead>"
            f"<tbody>{''.join(health_rows)}</tbody></table>"
        )
    return f'<section class="health"><h2>来源状态</h2>{errors}{table}</section>'
