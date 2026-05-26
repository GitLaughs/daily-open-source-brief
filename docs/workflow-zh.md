# 中文工作流程

本文描述从安装到日常使用的推荐流程。

## 1. 安装并验证

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

确认测试通过后，再配置真实采集和投递。

## 2. 配置来源

`config/sources.yml` 负责采集来源。

常见来源：

- `github.queries`：GitHub Search 查询。
- `github.trending`：GitHub Trending 配置，默认关闭。
- `rss`：RSS/Atom 订阅。
- `webpages`：公开网页列表。

建议先少量启用来源，确认质量后再扩展。

## 3. 配置插件

`config/plugins.yml` 负责插件开关。

常用命令：

```powershell
.\.venv\Scripts\python.exe -m app.cli plugin list
.\.venv\Scripts\python.exe -m app.cli plugin check
.\.venv\Scripts\python.exe -m app.cli plugin disable rss
.\.venv\Scripts\python.exe -m app.cli plugin enable rss
```

新增采集、摘要、渲染或发送能力时，优先写插件，不把逻辑继续塞进 `app/run_daily.py`。

## 4. 运行日报

离线 sample：

```powershell
.\.venv\Scripts\python.exe -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
```

真实运行：

```powershell
.\.venv\Scripts\python.exe -m app.cli run
```

只采集，不投递：

```powershell
.\.venv\Scripts\python.exe -m app.cli run --skip-mail --skip-lark
```

## 5. 使用本地知识库

搜索：

```powershell
.\.venv\Scripts\python.exe -m app.cli kb search EDA
```

查看最近内容：

```powershell
.\.venv\Scripts\python.exe -m app.cli kb recent
```

收藏或标记：

```powershell
.\.venv\Scripts\python.exe -m app.cli kb mark 123 favorite
.\.venv\Scripts\python.exe -m app.cli kb mark 123 read
.\.venv\Scripts\python.exe -m app.cli kb tag 123 open-source
```

## 6. 投递到邮件或 Lark

邮件需要 `.env` 中配置 SMTP。

Lark/飞书需要先准备本机可用的 `lark-cli` 身份，再设置：

```text
LARK_SEND=1
LARK_AS=bot
LARK_USER_ID=
LARK_CHAT_ID=
```

建议首次运行时先加 `--skip-mail --skip-lark`，确认摘要内容无误后再打开投递。

## 7. 自动运行

Windows：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-windows-task.ps1 -DailyAt 08:00
```

Linux：

```bash
bash scripts/install-linux.sh
```

## 8. 发布前检查

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
git status --short
```

发布前确认没有提交：

- `.env`
- `data/`
- `logs/`
- `public/archive/`
- `config/profile.yml`
- 私密 ID、token、密码、服务器地址

