# daily-open-source-brief v0.2.0｜Windows 新手安装与插件增强

This release adds a Chinese Windows onboarding path, one-command install/test scripts, GitHub Actions CI, and a broader plugin pipeline for enrichment, delivery, and digest operations.

中文关键词：开源日报、Windows 安装、GitHub 项目摘要、RSS 摘要、网页采集、SQLite FTS5、知识库、插件管线、自动化日报。

## Highlights

- Added `README.zh-CN.md`, `docs/install-windows.md`, and `docs/workflow-zh.md`.
- Added Windows scripts for install, validation, and optional scheduled task registration.
- Added GitHub Actions CI on Windows and Linux.
- Added optional GitHub Trending collection.
- Added enricher plugins for feedback weights, deadline extraction, cross-source dedupe, and important-item Lark digests.
- Added LLM retry helpers, weekly metrics, Lark bot helpers, Webhook delivery, and Jinja HTML email templates.
- Expanded tests to cover deadline extraction, dedupe, feedback weights, retry behavior, metrics, senders, and plugin behavior.
- Public package keeps runtime secrets, generated archives, local profiles, databases, private IDs, and deployment targets out of git.

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

- 51 unit tests pass.
- `git diff --check` passes.
- Windows script validation passes when dependencies can be installed.
- Sample run writes a local archive under `public/archive/`.
