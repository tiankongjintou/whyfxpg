# ADR-004：大屏 UI 拆分出 DashboardReadModel 与 BigScreenPresenter

## 状态

已接受（Accepted），2026-07-29。

## 背景

`whyfxpg/webui/bigscreen.py` 中的 `render_bigscreen()` 同时做：

1. 从 SQLite 查询汇总、趋势、国别、危害、预警等数据。
2. 使用 pandas 做数据转换（列重命名、索引设置、空值处理）。
3. 调用 Streamlit 组件（`st.metric`、`st.line_chart`、`st.bar_chart`、`st.dataframe`）渲染。

这导致：

- 认知复杂度高，无法单元测试。
- 任何数据查询的改动都会牵动 UI 文件。
- 测试必须导入 `streamlit`，而 Streamlit 在 headless 环境外会触发网络/端口行为。

## 决策

拆成三层：

| 层 | 文件 | 职责 |
|---|---|---|
| Read Model | `whyfxpg/webui/read_model.py` | 无 Streamlit 依赖的数据库查询，返回 pandas DataFrame / dict。 |
| Presenter | `whyfxpg/webui/presenters/bigscreen_presenter.py` | 把 `DashboardReadModel` 的结果转换为 `BigScreenViewModel`（纯数据对象）。 |
| View | `whyfxpg/webui/bigscreen.py` | 只负责调用 Streamlit 组件渲染 `BigScreenViewModel`。 |

同时，原有 `whyfxpg/webui/queries.py` 变成 `DashboardReadModel` 的 Streamlit 缓存包装层，
`app.py` 其他页面无需改动。

### 关键原则

- **View 不直接查数据库**：`render_bigscreen(view_model=None)` 接收可选的 `BigScreenViewModel`；缺省时才新建 `DashboardReadModel` + `BigScreenPresenter`。
- **Presenter 可独立测试**：通过注入 fake `DashboardReadModel`，可以在不导入 streamlit 的情况下断言数据转换结果。
- **缓存不污染核心逻辑**：Streamlit 的 `@st.cache_data` 只留在 `queries.py` 薄包装中，不进入 `read_model` 或 `presenter`。
- **纯 Streamlit 原生组件**：继续不引入 `streamlit-echarts` / `pyecharts` / `folium` 等第三方大屏库。

## 影响

### 新增文件

- `whyfxpg/webui/read_model.py`
- `whyfxpg/webui/presenters/__init__.py`
- `whyfxpg/webui/presenters/bigscreen_presenter.py`
- `whyfxpg/tests/test_bigscreen_presenter.py`

### 修改文件

- `whyfxpg/webui/bigscreen.py`：改为接收 `BigScreenViewModel` 并渲染，移除所有数据库查询。
- `whyfxpg/webui/queries.py`：改为 `DashboardReadModel` 的缓存包装层。

### 不变

- `whyfxpg/webui/app.py` 对 `render_bigscreen()` 的调用方式不变。
- 大屏展示效果不变（指标、趋势图、危害 Top10、国别 Top10、风险等级、事件列表、预警列表）。

## 测试

- 新增 5 条 presenter 测试，覆盖：
  - 空 view model 默认值。
  - fake read model 数据经 presenter 后字段正确。
  - 预警列表自动截断为 Top 10。
  - 空数据库情况。
  - 真实 `DashboardReadModel` + 空 `initialized_db` 的冒烟测试。
- 测试文件不导入 `streamlit`。
- 全量 pytest 通过：65 passed。

## 后续可选

- 将风险总览、人工复核、预警中心等页面也拆出 presenter + read model，统一 UI 架构。
- 用 `read_model` 逐步替换 `queries.py` 中的直接 SQL，最终 deprecate `queries.py` 中的缓存包装。
- 新增 `DashboardReadModel` 单测，不依赖 presenter。
