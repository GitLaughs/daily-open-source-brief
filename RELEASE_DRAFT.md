# daily-open-source-brief v0.3.0｜网页与期刊源增强

This release expands research discovery with arXiv and journal feed presets, adds RSS 1.0 / RDF parsing for namespaced feed metadata, and makes public-source HTTP fetching proxy-safe by default.

中文关键词：开源日报、论文日报、期刊 RSS、arXiv、网页采集、SQLite FTS5、知识库、插件管线、自动化日报。

## Highlights

- Added RSS 1.0 / RDF parser support, including namespaced `dc:*`, `content:*`, and `rdf:about` metadata.
- Enabled arXiv feeds for CS.AI, CS.LG, CS.AR, EESS.SP, and EESS.SY.
- Added Nature Electronics, Nature Machine Intelligence, and Science Robotics journal feed presets.
- Included academic papers and journal articles in recent web item loading for digest selection.
- Added a shared HTTP client for GitHub, RSS, Trending, and webpage fetchers.
- HTTP fetches now ignore system proxy settings by default; set `DAILY_BRIEF_TRUST_ENV_PROXY=1` to opt in.
- Added parser coverage for RDF journal-style feeds and HTTP proxy behavior.
- Keeps the v0.2.x Windows onboarding, CI, plugin pipeline, and SQLite connection cleanup improvements.

## Runtime

Python 3.10+ and SQLite with FTS5 support are recommended. Live GitHub collection works best with `GITHUB_TOKEN`. SMTP, Lark, Webhook, and OpenAI-compatible LLM settings are optional and must be supplied through a local `.env` file.

Windows quick install:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

## Verify

```powershell
python -m pytest
python -m unittest discover -s tests -v
git diff --check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
python -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
python -m app.cli kb search Python
```

Expected:

- 54 unit tests pass.
- `git diff --check` passes.
- Windows script validation passes when dependencies can be installed.
- Sample run writes a local archive under `public/archive/`.
