# ADR-011: Web UI 页面拆分为 `whyfxpg/webui/screens/`

## 状态

已采纳（Phase 4B）

## 背景

`whyfxpg/webui/app.py` 最初承载了 8 个页面的全部渲染逻辑，文件长度超过 420 行。随着页面增多，出现以下问题：

- **单一职责违反**：app.py 既要处理全局配置、侧边栏导航，又要维护每个页面的数据筛选、表单、SQL 查询。
- **并行编辑冲突**：所有页面改动都落在同一个文件，单人开发时也容易造成频繁的原地修改。
- **测试困难**：页面逻辑与 Streamlit 渲染混在同一个 if/elif 链中，无法单独对某页面做单元测试。

## 决策

1. 在 `whyfxpg/webui/screens/` 下为每个页面建立独立模块，暴露统一的 `render() -> None` 函数。
2. `app.py` 只负责：
   - `st.set_page_config` 全局配置；
   - 侧边栏 `st.sidebar.radio` 导航；
   - 根据用户选择调用 `PAGES[page]()`。
3. 继续使用现有的 `whyfxpg/webui/queries.py` 作为数据查询缓存层，不重复实现查询。
4. **不使用 Streamlit 自动 multipage 的 `pages/` 目录**，避免自动导航与自定义 radio 导航两套系统并存。

## 页面映射

| 导航标签 | 模块 | 职责 |
|---|---|---|
| 📊 风险总览 | `screens/overview.py` | 汇总指标、国别分布、高风险事件 |
| 🖥️ 风险态势大屏 | `screens/bigscreen.py` | 包装 `whyfxpg.webui.bigscreen` |
| 📋 风险事件 | `screens/risk_events.py` | 列表与筛选器 |
| ✅ 人工复核 | `screens/review.py` | 复核表单与历史 |
| 🔔 预警中心 | `screens/alerts.py` | 预警列表与筛选 |
| 📄 报告中心 | `screens/reports.py` | 报告列表与生成按钮 |
| 🔗 因果知识图谱 | `screens/causal.py` | 因果解释与反事实推理 |
| 🌐 数据源监控 | `screens/sources.py` | 数据源状态列表 |

## 影响

- `app.py` 从 421 行缩减至约 60 行，职责清晰。
- 新增页面时，只需创建 `screens/<name>.py` 并在 `screens/__init__.py` 的 `PAGES` 字典中注册。
- 页面内仍可直接使用 Streamlit API，迁移成本低。
- 测试侧可以单独导入某个 `screens/*.py` 模块并断言其 `render` 函数存在与可调用，无需运行 Streamlit 完整应用。

## 后续工作

- Phase 4C：把 `screens/review.py` 中的直接 SQL 写入抽取为 `ReviewService`，进一步剥离数据写入与页面渲染。
- 若未来需要真正的多页面 URL 路由，再评估 Streamlit 原生 `pages/` 方案，届时需要移除自定义 radio 导航。

## 兼容性

- 用户入口保持不变：`streamlit run whyfxpg/webui/app.py`。
- 页面之间的切换逻辑和显示内容与原实现一致，无行为变更。
