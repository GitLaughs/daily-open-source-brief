# daily-open-source-brief

Plugin-based daily brief generator for GitHub projects, RSS feeds, public webpages, and a local searchable knowledge base.

Keywords: open-source brief, GitHub trending digest, RSS digest, webpage collector, SQLite FTS5, knowledge base, plugin pipeline, Lark sender, email digest, Python automation, daily report.

`daily-open-source-brief` turns noisy public sources into a searchable daily digest:

- collector plugins fetch GitHub repositories, RSS/Atom feeds, and public webpage lists;
- scoring keeps recent, active, and topic-relevant items near the top;
- summarizer plugins can use an OpenAI-compatible endpoint or deterministic fallback text;
- renderer plugins save digest records and HTML archive output;
- sender plugins can deliver through SMTP or Lark when configured locally;
- SQLite stores items, source health, plugin runs, feedback, tags, and digest history;
- FTS5 search makes collected items reusable from CLI now and a future web console later;
- feedback marks support favorite, read, later, blocked, and not-interested states.

This repository contains source code, templates, tests, and generic example configuration only. It does not contain runtime databases, local profiles, API keys, private user IDs, private chat IDs, server addresses, generated archives, or local `.env` files.

## Why This Exists

Useful open-source and engineering updates arrive through different channels:

- GitHub search catches active repositories but misses articles and notices;
- RSS feeds are structured but vary in quality;
- public webpage lists are common for organizations that do not publish feeds;
- email or chat delivery is useful, but the collected content should remain searchable after the daily message is sent.

This project keeps those jobs separate through a plugin pipeline:

| Stage | Job |
|---|---|
| `provider` | Configure LLM/provider runtime |
| `collector` | Fetch GitHub, RSS, and webpage candidates |
| `summarizer` | Generate digest text |
| `renderer` | Save digest records and HTML archive |
| `sender` | Deliver through configured channels |

## Architecture

```mermaid
flowchart LR
    A[GitHub search] --> D[collector plugins]
    B[RSS and Atom feeds] --> D
    C[Public webpage lists] --> D
    D --> E[SQLite items]
    E --> F[Rank and dedupe]
    F --> G[Summarizer]
    G --> H[Renderer]
    H --> I[HTML archive]
    H --> J[Digest table]
    G --> K[Mail or Lark sender]
    E --> L[FTS5 search index]
    L --> M[Knowledge CLI]
```

## Features

- Plugin registry and config-driven pipeline in `config/plugins.yml`.
- Built-in collectors for GitHub repositories, RSS/Atom entries, and public webpage list pages.
- Local plugin loading from `plugins/local/*.py`.
- SQLite persistence for sources, items, repo snapshots, digests, source runs, plugin health, tags, and feedback.
- SQLite FTS5 search index for item title, snippet, URL, and source type.
- Knowledge API in `app/knowledge.py` for CLI and future web-console reuse.
- Knowledge CLI for search, recent items, saved items, marks, and tags.
- Existing `app.brief_cli` entry kept for compatibility.
- Deterministic fallback summaries when LLM configuration is absent.
- Optional OpenAI-compatible LLM configuration.
- Optional SMTP and Lark delivery.
- HTML archive generation with retention cleanup.
- Unit tests for collectors, rendering, plugin management, FTS, knowledge operations, and CLI behavior.

## Requirements

- Python 3.10+
- SQLite with FTS5 support
- Network access for live GitHub/RSS/webpage collection
- Optional: GitHub token for higher GitHub API limits
- Optional: SMTP credentials or `lark-cli` identity for delivery

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Quick Start

Run an offline sample without sending messages:

```powershell
python -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
```

Search the local knowledge base:

```powershell
python -m app.cli kb search Python
python -m app.cli kb recent
python -m app.cli kb mark 1 favorite
python -m app.cli kb mark 1 read
python -m app.cli kb tag 1 open-source
python -m app.cli kb saved
```

Manage plugins:

```powershell
python -m app.cli plugin list
python -m app.cli plugin check
python -m app.cli plugin disable rss
python -m app.cli plugin enable rss
python -m app.cli plugin status
```

## Configuration

Copy `.env.example` to `.env` locally and fill only the providers you need. `.env` is ignored by git.

Required for live GitHub collection:

```text
GITHUB_TOKEN=
```

Optional mail delivery:

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
MAIL_TO=
MAIL_FROM=
```

Optional OpenAI-compatible summarization:

```text
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=
```

Optional Lark delivery:

```text
LARK_SEND=1
LARK_AS=bot
LARK_USER_ID=ou_xxx
```

Public sources live in `config/sources.yml`. The included webpage source is a disabled example; replace it with public pages you are allowed to fetch.

## Plugin Development

New collectors, summarizers, renderers, senders, providers, and scoring strategies should be plugins.

- Built-in plugins live in `app/plugins/builtins.py`.
- Local plugins live in `plugins/local/*.py`.
- Local plugins expose `register(registry)`.
- Plugin switches and options live in `config/plugins.yml`.
- Shared runtime data goes through `PluginContext.state`.
- New plugins should include focused tests.

## Knowledge Base

The knowledge layer is intentionally SQL-backed and small:

- `items_fts` mirrors item title, snippet, URL, and source type.
- `item_tags` stores reusable labels.
- `item_feedback` stores favorite/read/later/blocked/not-interested marks.
- `app/knowledge.py` is the public API for CLI and future web UI.

Current commands:

```bash
python -m app.cli kb search EDA
python -m app.cli kb recent
python -m app.cli kb mark 123 favorite
python -m app.cli kb mark 123 read
python -m app.cli kb tag 123 open-eda
python -m app.cli kb saved
```

## Verify

```powershell
python -m unittest discover -s tests -v
git diff --check
```

Expected:

- collector parser tests pass;
- plugin registry and plugin health tests pass;
- FTS search tests pass;
- knowledge mark/tag/saved tests pass;
- CLI tests pass.

## Security

- Do not commit `.env`, `config/profile.yml`, SQLite databases, generated archives, logs, or local deployment packages.
- Use `.env.example` for public examples.
- Keep deployment hosts, private user IDs, private chat IDs, and API tokens out of the repository.
- Treat `plugins/local/` as local extension space; review local plugins before publishing.

## License

MIT. See [LICENSE](LICENSE).
