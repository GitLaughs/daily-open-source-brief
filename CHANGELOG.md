# Changelog

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
