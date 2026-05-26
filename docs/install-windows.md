# Windows 安装指导

本文面向第一次使用 `daily-open-source-brief` 的 Windows 用户。

## 1. 安装 Python

安装 Python 3.10 或更新版本：

```powershell
python --version
```

如果命令不存在，安装 Python 后重新打开 PowerShell。

建议安装时勾选 `Add python.exe to PATH`。

## 2. 获取项目

如果已经下载 ZIP，先解压到一个固定目录。

如果使用 Git：

```powershell
git clone https://github.com/GitLaughs/daily-open-source-brief.git
cd daily-open-source-brief
```

## 3. 一键安装

在项目根目录运行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

脚本会创建 `.venv`、安装依赖、生成 `.env`，并运行离线示例。

如果网络需要代理：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1 -Proxy http://127.0.0.1:7890
```

## 4. 离线验证

安装后可重复运行：

```powershell
.\.venv\Scripts\python.exe -m app.cli run --sample --skip-web --skip-rss --skip-mail --skip-lark --force-send
```

成功后会在 `public/archive/` 下生成本地 HTML 归档。

## 5. 配置真实采集

打开 `.env`，按需填写：

```text
GITHUB_TOKEN=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=
```

邮件投递：

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
MAIL_TO=
MAIL_FROM=
```

Lark/飞书投递：

```text
LARK_SEND=1
LARK_AS=bot
LARK_USER_ID=
LARK_CHAT_ID=
```

没有这些配置时，仍可运行离线示例和本地知识库命令。

## 6. 常用工作流

运行日报：

```powershell
.\.venv\Scripts\python.exe -m app.cli run
```

只检查插件配置：

```powershell
.\.venv\Scripts\python.exe -m app.cli plugin check
```

查看插件状态：

```powershell
.\.venv\Scripts\python.exe -m app.cli plugin status
```

搜索历史内容：

```powershell
.\.venv\Scripts\python.exe -m app.cli kb search Python
```

## 7. 注册 Windows 计划任务

可选：每天固定时间自动运行。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-windows-task.ps1 -TaskName daily-open-source-brief -DailyAt 08:00
```

查看任务：

```powershell
Get-ScheduledTask -TaskName daily-open-source-brief
```

删除任务：

```powershell
Unregister-ScheduledTask -TaskName daily-open-source-brief -Confirm:$false
```

## 8. 常见问题

### pip 安装失败

先确认网络和代理。如果你使用本地代理：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

日报采集默认不读取系统代理，避免 Windows 注册表代理影响公开来源抓取。如果运行时确实需要代理，在 `.env` 中显式开启：

```text
DAILY_BRIEF_TRUST_ENV_PROXY=1
```

### PowerShell 禁止运行脚本

只放开当前窗口：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 没有 GitHub token

离线 sample 可以运行。真实 GitHub 采集建议配置 `GITHUB_TOKEN`，否则可能遇到 API 限流。
