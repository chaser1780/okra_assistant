# 独立大系统目录结构与迁移方案

## 目标

把原先“`C:` 上的 skill 代码 + `F:` 上的数据目录”升级为一个完整可复制的独立工程：

- 项目名称：`okra assistant`
- 项目根目录：`F:\okra_assistant`

## 迁移原则

- 不改变现有功能与运行方式
- 不降低模型、抓取、桌面壳性能
- 新增缓存、日志、临时文件继续优先落在 `F:`
- 保留旧路径兼容，避免现有任务或快捷方式失效

## 新的工程形态

### 代码

- 原 skill 中的核心代码已迁入：
  - `F:\okra_assistant\scripts`
  - `F:\okra_assistant\assets`
  - `F:\okra_assistant\references`
  - `F:\okra_assistant\agents`

### 数据与运行产物

- 原 `F:\okra_assistant` 已整体升级为项目根的内容：
  - `config`
  - `raw`
  - `db`
  - `reports`
  - `docs`
  - `logs`
  - `temp`
  - `cache`
  - `app`

### 启动入口

- `run_daily_report.ps1`
- `run_nightly_review.ps1`
- `run_desktop_app.ps1`

## 兼容策略

- 旧路径 `F:\okra_assistant` 保留为兼容入口
- 这样历史脚本、快捷方式和计划任务不会立刻失效

## 已完成的迁移动作

1. 创建新项目根：`F:\okra_assistant`
2. 迁移原 `F:\okra_assistant` 内容到新项目根
3. 复制原 skill 代码与资源到新项目根
4. 保留旧路径 `F:\okra_assistant` 兼容
5. 更新默认路径与启动器到 `F:\okra_assistant`
6. 更新桌面壳默认根目录到 `F:\okra_assistant`
7. 更新模型 API key 文件路径到新根目录

## 后续建议

### 可立即做

- 把计划任务显式改到 `F:\okra_assistant`
- 把桌面快捷方式目标显式改到 `F:\okra_assistant`

### 可延后做

- 清理 `F:\okra_assistant` 中的旧 skill 副本
- 补 `pyproject.toml` 或项目级版本信息
- 增加打包与发布脚本

## 结论

现在 `okra assistant` 已经从 skill 形态升级为独立项目形态：

- 可复制
- 可备份
- 可继续扩展为大系统
- 不再以 Codex skill 为运行前提
