# okra assistant 开发任务清单

- 文档定位：当前版本后的执行清单
- 依赖文档：`F:\okra_assistant\docs\improvement_recommendations.md`
- 更新日期：2026-03-11

## 状态说明

- `[todo]` 尚未开始
- `[doing]` 正在实施
- `[done]` 已完成
- `[blocked]` 存在外部依赖或等待决策

## 当前说明

- 当前运行主源已经切换到：
  - `db/long_memory`
  - `db/execution_sync`
  - `db/portfolio_state`
- 历史目录 `db/review_memory` 与 `db/trade_journal` 已降为迁移/归档语义，不再作为默认运行态依赖。
- 当前主入口以 `README.md`、`project.toml`、`docs/modern_workbench.md` 为准。

## 当前关注事项

- `[done]` Today analysis、execution sync、long memory、workbench API 与前端主路径已经切到新真源
- `[done]` 历史交易/记忆旧脚本已删除
- `[done]` 关键测试 fixture 已迁到 `execution_sync` / `long_memory`
- `[doing]` 活跃文档全面清洗与历史文档过时说明补齐
- `[doing]` 全仓文本卫生检查与残余乱码收口

## 后续建议

1. 持续缩减兼容层，逐步移除仅服务历史数据回灌的 helper。
2. 在前端做 route-level code splitting，解决当前 Vite 大包 warning。
3. 持续补齐文档，使当前有效文档全部可直接交接给新实现者。
