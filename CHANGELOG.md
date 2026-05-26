# Changelog

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
