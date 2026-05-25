# Agent Instructions

本仓库新增或改造功能时，默认走插件架构。

## 插件优先

- 新采集来源、评分策略、摘要方式、渲染输出、发送渠道、LLM/provider 选择，都优先做成插件。
- 插件实现放在 `app/plugins/`。内置插件注册在 `app/plugins/builtins.py`。
- 本地插件放在 `plugins/local/*.py`，文件中暴露 `register(registry)`。
- 插件开关和参数放在 `config/plugins.yml`，不要继续把新功能硬编码进 `app/run_daily.py`。
- `app/runner.py` 负责执行管线；`app/run_daily.py` 只保留旧入口兼容。
- 新的管理命令放在 `app/cli.py`，优先扩展这里，不要再新增零散脚本入口。

## 当前插件阶段

- `provider`: 配置 LLM/provider，例如 `ccswitch`。
- `collector`: 采集候选内容，例如 `github`、`webpage`、`rss`。
- `summarizer`: 生成日报正文。
- `renderer`: 生成 HTML、写归档、保存 digest。
- `sender`: 投递渠道，例如 `lark`、`mail`。

## 开发要求

- 新插件继承 `BasePlugin`，返回 `PluginResult`。
- 新插件要声明 `name`、`kind`、`version`、`description`。
- 共享运行数据写入 `PluginContext.state`。
- 单个来源失败应尽量记录到 result 或 source health，不应无故阻断其它插件。
- 插件运行状态由 `plugin_runs` / `plugin_health` 记录。
- 保持旧 CLI 参数兼容；新增开关优先映射到插件配置或 CLI override。
- 新增插件必须补 `tests/test_plugins.py` 或对应模块测试。
