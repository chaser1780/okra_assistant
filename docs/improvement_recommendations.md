# okra assistant 改进建议

- 文档定位：面向后续演进的改进清单
- 适用范围：`F:\okra_assistant`
- 更新日期：2026-03-11

## 当前前提

- 当前运行主源：
  - `db/long_memory`
  - `db/execution_sync`
  - `db/portfolio_state`
- 当前主入口：
  - `python scripts/run_today_analysis.py --date YYYY-MM-DD`
  - `python scripts/run_long_memory_analysis.py --date YYYY-MM-DD`
  - 工作台与页级 API 说明见 `docs/modern_workbench.md`
- 历史目录 `db/review_memory`、`db/trade_journal` 与历史脚本不再作为默认运行态依赖。

## 建议优先级

### P0

1. 继续缩减历史兼容层
2. 保持 API 契约、测试 fixture、迁移脚本与当前真源一致
3. 保持全仓文本卫生检查通过

### P1

1. 继续清理历史文档与历史术语
2. 强化 learning ledger、replay summary、system runtime 的结构化展示
3. 补更多迁移专项测试，确保 `db/legacy/*` 可追溯

### P2

1. 前端 route-level code splitting
2. bundle 体积优化
3. 更细的页级 DTO 收紧与渲染拆分
