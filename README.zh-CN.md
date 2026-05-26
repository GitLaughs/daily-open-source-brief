# daily-open-source-brief 中文指南

`daily-open-source-brief` 是一个插件化的每日信息简报工具，用来采集 GitHub 项目、RSS/Atom 订阅、公开网页列表，并生成可搜索、可归档、可投递的日报。

适合这些场景：

- 每天跟踪开源项目、技术新闻、学校或组织公开通知。
- 把零散来源整理成一份中文摘要。
- 在本地 SQLite 中保留历史记录，后续可以搜索、收藏、标记已读。
- 通过邮件或 Lark/飞书投递日报。

## 快速开始：Windows

要求：

- Windows 10/11
- Python 3.10 或更新版本
- PowerShell 5.1 或 PowerShell 7

一键安装并运行离线示例：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

安装脚本会完成：

- 创建 `.venv` 虚拟环境。
- 安装 `requirements.txt` 中的依赖。
- 如果没有 `.env`，从 `.env.example` 复制一份。
- 运行一次离线 sample，不发送邮件和 Lark 消息。

更多说明见 [Windows 安装指导](docs/install-windows.md)。

## 常用命令

运行一次离线示例：

```powershell
.\.venv\Scripts\python.exe -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
```

运行真实采集：

```powershell
.\.venv\Scripts\python.exe -m app.cli run
```

搜索本地知识库：

```powershell
.\.venv\Scripts\python.exe -m app.cli kb search EDA
.\.venv\Scripts\python.exe -m app.cli kb recent
.\.venv\Scripts\python.exe -m app.cli kb saved
```

管理插件：

```powershell
.\.venv\Scripts\python.exe -m app.cli plugin list
.\.venv\Scripts\python.exe -m app.cli plugin check
.\.venv\Scripts\python.exe -m app.cli plugin disable rss
.\.venv\Scripts\python.exe -m app.cli plugin enable rss
```

完整工作流程见 [中文工作流程](docs/workflow-zh.md)。

## 配置

复制 `.env.example` 为 `.env` 后，按需填写：

```text
GITHUB_TOKEN=
OPENAI_API_KEY=
SMTP_HOST=
SMTP_USER=
SMTP_PASS=
MAIL_TO=
MAIL_FROM=
LARK_SEND=0
```

没有 LLM、邮件、Lark 配置时，程序仍可用确定性模板生成摘要，并保存本地归档。

公开采集来源在 `config/sources.yml` 中配置；插件开关和参数在 `config/plugins.yml` 中配置。

## 插件架构

新增采集来源、摘要方式、渲染输出、发送渠道、LLM provider 时，优先做成插件。

插件阶段：

- `provider`：配置 LLM/provider。
- `collector`：采集候选内容。
- `enricher`：打分、去重、截止日期、重要消息筛选等增强处理。
- `summarizer`：生成日报正文。
- `renderer`：生成 HTML、写归档、保存 digest。
- `sender`：邮件、Lark、Webhook 等投递渠道。

内置插件在 `app/plugins/builtins.py`，本地插件可放到 `plugins/local/*.py`，并暴露 `register(registry)`。

## 验证

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

脚本会安装测试依赖并运行：

- `python -m pytest`
- `git diff --check`

## 发布边界

仓库只应包含源码、模板、测试和通用示例配置。不要提交：

- `.env`
- `config/profile.yml`
- SQLite 数据库
- 生成的 HTML 归档
- 日志
- API key、邮箱密码、真实用户 ID、真实群 ID、私有服务器地址

