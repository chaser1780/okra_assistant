# okra assistant 改造执行路线图

- 文档定位：当前可持续执行的改造路线图
- 适用范围：`F:\okra_assistant`
- 更新日期：2026-03-13

## 当前基线

- 运行主源已经切换到：
  - `db/long_memory`
  - `db/execution_sync`
  - `db/portfolio_state`
- 统一 today orchestrator、页级 API、Router + React Query 主路径已经落地。
- 历史交易/记忆旧脚本已删除。
- 历史目录 `db/review_memory`、`db/trade_journal` 仅保留迁移/归档意义。

## 接下来的执行顺序

### 1. 继续收口兼容层

- 逐步移除只为历史数据回灌保留的 helper
- 把剩余 `review_memory` 命名收敛为中性兼容视图命名
- 保证 replay / learning / workbench 状态全部围绕新真源

### 2. 完成文档现代化

- 持续更新当前有效文档
- 对历史文档统一标注“历史背景，不代表当前运行主源”
- 保证新实现者只看 README、project.toml、modern_workbench 也不会误入旧路径

### 3. 做性能与体验层收尾

- 前端 route-level code splitting
- 降低 Vite 主包体积 warning
- 补更细的 task/runtime 可视化与历史诊断页
