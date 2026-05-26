# Changelog

## v0.3.0 - 2026-05-26

Research feed discovery and proxy-safe fetching update.

### Highlights

- Added a shared HTTP client for GitHub, RSS, Trending, and webpage fetchers.
- Public-source HTTP fetches ignore environment proxy settings by default; set `DAILY_BRIEF_TRUST_ENV_PROXY=1` to opt in.
- Added RSS 1.0 / RDF feed parsing for journal feeds that publish namespaced RSS items.
- Added enabled arXiv research feeds for AI, machine learning, computer architecture, signal processing, and systems.
- Added journal feed presets for Nature Electronics, Nature Machine Intelligence, and Science Robotics.
- Included `academic_paper` and `journal_article` in recent web item loading so research sources appear in digest selection.
- Added RDF feed parser and HTTP proxy behavior coverage.

### Verify

- `python -m pytest` (54 tests)
- `git diff --check`

## v0.2.1 - 2026-05-26

Patch release for Windows CI reliability.

### Fixes

- Close SQLite connections when using `with db.connect(...)` so Windows can delete temporary database files after tests.

### Verify

- `python -m pytest`
- `git diff --check`

## v0.2.0 - 2026-05-26

Windows onboarding, richer plugin stages, and expanded delivery workflow.

### Highlights

- Added Chinese README, Windows install guide, and Chinese daily workflow guide.
- Added `scripts/install-windows.ps1`, `scripts/test.ps1`, and `scripts/register-windows-task.ps1`.
- Added GitHub Actions CI across Windows and Linux Python versions.
- Added optional GitHub Trending collector and enricher plugins for feedback weights, deadline extraction, cross-source dedupe, and Lark digest filtering.
- Added deadline, dedupe, feedback, LLM retry, weekly metrics, Lark bot, and HTML email/template support.
- Expanded SQLite state with deadline events and improved plugin health/run tracking.
- Improved RSS and webpage fetch behavior, including parallelism and optional detail fetching.

### Verify

- `python -m pytest`
- `python -m unittest discover -s tests -v`
- `git diff --check`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

## v0.1.0 - 2026-05-25

Initial public release.

### Highlights

- Plugin-based daily brief pipeline with provider, collector, summarizer, renderer, and sender stages.
- Built-in GitHub, RSS/Atom, and public webpage collectors.
- SQLite storage for collected items, snapshots, digests, source health, plugin health, tags, and feedback.
- SQLite FTS5 knowledge-base search for title, snippet, URL, and source type.
- Knowledge CLI commands for search, recent items, marks, tags, and saved items.
- Optional SMTP and Lark delivery hooks.
- Generic public sample configuration with runtime secrets and generated data excluded.

### Runtime

- Requires Python 3.10+ and SQLite with FTS5 support.
- Live collection credentials stay in local `.env` files.

### Verify

- `python -m unittest discover -s tests -v`
- `python -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send`
