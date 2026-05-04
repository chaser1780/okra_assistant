# okra assistant

`okra assistant` 是一个本地运行的个人基金研究与调仓助手系统。

它当前具备：

- 基金净值与新闻抓取
- 盘中代理行情与基金估值
- 多智能体研究与委员会式建议
- 规则校验与中文报告
- 交易记录与持仓自动回写
- 夜间复盘与记忆更新
- 本地桌面壳

## 目录结构

```text
F:\okra_assistant
├─ app                  桌面壳、图标、启动辅助脚本
├─ agents               模型/agent 相关静态配置
├─ assets               报告模板等资源
├─ cache                缓存与 pycache
├─ config               组合、策略、模型、agent 配置
├─ db                   结构化数据库式输出
├─ docs                 设计文档、迁移文档、handoff
├─ logs                 任务日志、模型日志、桌面日志
├─ raw                  原始行情与新闻快照
├─ references           评分与来源策略说明
├─ reports              人类可读报告
├─ scripts              核心 Python 代码
├─ temp                 临时目录
├─ run_daily_report.ps1 日内任务启动脚本
├─ run_nightly_review.ps1 夜间复盘启动脚本
└─ run_desktop_app.ps1  桌面壳启动脚本
```

## 关键入口

- 桌面壳入口：`F:\okra_assistant\app\desktop_app.py`
- Qt 桌面主壳：`F:\okra_assistant\app\desktop_shell_qt.py`
- 日内全链路：`F:\okra_assistant\scripts\run_daily_pipeline.py --mode intraday`
- 夜间复盘：`F:\okra_assistant\scripts\run_daily_pipeline.py --mode nightly`
- 交易录入：`F:\okra_assistant\scripts\record_trade.py`
- 项目版本文件：`F:\okra_assistant\project.toml`
- 备份脚本：`F:\okra_assistant\backup_okra_assistant.ps1`

## 桌面架构

- 当前桌面端已统一为 `PySide6 / Qt`
- `Tk` 旧壳与其配套视图代码已从主代码路径移除
- 启动脚本默认按 Qt 单栈启动

## 当前定位

- 这是独立项目本体。
- 原来的 Codex skill 目录仅作为历史来源保留，不再是运行依赖。
- 现在只保留 `F:\okra_assistant` 作为唯一项目根目录。

## 文档入口

- 文档索引：`F:\okra_assistant\docs\INDEX.md`
- 改造路线图：`F:\okra_assistant\docs\improvement_execution_roadmap.md`
- 开发任务清单：`F:\okra_assistant\docs\development_todo.md`
- 改进建议：`F:\okra_assistant\docs\improvement_recommendations.md`

## 备份

- 默认备份整个项目到：`F:\okra_assistant\backups`
- 执行命令：

```powershell
powershell -ExecutionPolicy Bypass -File "F:\okra_assistant\backup_okra_assistant.ps1"
```

- 若不想备份日志：

```powershell
powershell -ExecutionPolicy Bypass -File "F:\okra_assistant\backup_okra_assistant.ps1" -ExcludeLogs
```
