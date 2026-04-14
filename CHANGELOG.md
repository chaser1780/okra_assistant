# CHANGELOG

## 0.2.0 - 2026-03-10

- 将项目从 `skill + data` 形态升级为独立工程 `F:\okra_assistant`
- 清理旧的 `C:\Users\qmq\.codex\skills\fund-daily-brief` 副本
- 取消 `F:\fund_agent_data` 兼容入口，统一只保留 `F:\okra_assistant`
- 修复真实多智能体 SSE 传输稳定性，打通 `risk_manager` 与 `portfolio_trader`
- 修复最终建议层真实直出稳定性，减少对 fallback 的依赖
- 增加 `project.toml` 项目版本文件
- 增加 `backup_okra_assistant.ps1` 一键备份脚本
- 增强桌面壳，支持：
  - 手动触发日内/夜间任务
  - 交易录入与持仓自动回写
  - 日内研究、智能体、复盘和设置页
- 桌面入口更名为 `okra的小助手`

## 0.1.0 - 2026-03-09

- 建立基金研究系统基础链路
- 接入基金净值、新闻、盘中代理与基金估值
- 建立多智能体研究与委员会式建议流程
- 增加规则校验、中文报告、交易流水与复盘记忆
- 建立桌面壳初版与任务计划脚本
