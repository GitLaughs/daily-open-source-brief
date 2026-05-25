# daily-open-source-brief v0.1.0｜插件化日报和本地知识库

Initial public release of a plugin-based daily brief generator for GitHub repositories, RSS/Atom feeds, public webpage lists, and a local SQLite knowledge base.

中文关键词：开源日报、GitHub 项目摘要、RSS 摘要、网页采集、SQLite FTS5、知识库、插件管线、自动化日报。

## Highlights

- Plugin registry and config-driven pipeline with provider, collector, summarizer, renderer, and sender stages.
- Built-in collectors for GitHub search, RSS/Atom feeds, and public webpage list pages.
- SQLite persistence for items, source runs, plugin health, digests, tags, and feedback.
- FTS5-backed knowledge-base search over title, snippet, URL, and source type.
- `app/knowledge.py` provides reusable APIs for CLI and future web-console work.
- `python -m app.cli kb ...` commands support search, recent, saved, mark, and tag workflows.
- Optional OpenAI-compatible summarization, SMTP delivery, and Lark delivery stay locally configured.
- Public package contains generic example configuration only.

## Runtime

Python 3.10+ and SQLite with FTS5 support are required. Live GitHub collection works best with `GITHUB_TOKEN`. SMTP, Lark, and OpenAI-compatible LLM settings are optional and must be supplied through a local `.env` file.

This release does not include runtime databases, generated archives, local profiles, API keys, private user IDs, private chat IDs, private server addresses, or local `.env` files.

## Verify

```powershell
python -m unittest discover -s tests -v
git diff --check
python -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
python -m app.cli kb search Python
```

Expected:

- Unit tests pass.
- Sample run writes a local archive under `public/archive/`.
- Knowledge search returns the sample repository item after the sample run.
