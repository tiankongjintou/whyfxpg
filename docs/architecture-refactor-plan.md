# WHYFXPG 架构重构计划

## 决策：重构，不是重写

当前系统是一个**可运行、可测试、有实际业务价值**的初期系统：

- 已打通“采集 → 提取 → 评分 → 预警 → 可视化 → 报告”完整链路；
- 有 7+ 个 pytest 测试覆盖 DB、提取、评分、预警、采集、配置版本；
- Streamlit 看板已落地人工复核、因果解释、预警中心等页面；
- 评分模型包含海关业务特有概念：严重度/概率/国别/产品/历史/证据/因果因子。

完全重写会丢失上述已验证行为，并超出单人维护能力。因此选择**基于第一性原则的分阶段重构**：在不破坏功能的前提下，把浅模块加深、把泄漏的 seam 收窄、把全局状态改为可注入端口。

## 重构原则（来自 codebase-design 词汇）

1. **Deep modules**：把“实现复杂、接口简单”作为好模块的标准。`db.py` 已经是深模块（复杂 schema + 简单 `get_db_connection`），应继续让它负责连接与事务，而不是让业务模块各自开关连接。
2. **Seam / Adapter**：把外部依赖（LLM、HTTP 源、数据库、文件配置）变成可替换的端口。两个 adapter 才让 seam 成立。
3. **Locality**：改一个概念只改一个文件。当前“预警写入”出现在 `alert_engine.py` 和 `risk_predictor.py`，需要合并。
4. **Interface is the test surface**：新模块必须能脱离真实网络/数据库/Streamlit 测试。

## 阶段与目标

### Phase 1：建立数据访问 seam（UnitOfWork + Stores）

目标：解决 `database is locked` 与 WAL 补丁的表面症状，让整条 pipeline 在一次事务内完成，测试可注入内存连接。

状态：**已完成**（2026-07-29）。

- 1A：创建 `whyfxpg/core/stores.py`
  - `UnitOfWork`：上下文管理器，控制连接生命周期与提交/回滚；修复 `from_connection` 场景下 `__enter__` 会覆盖外部连接的 bug。
  - `AlertStore`：查询/插入 `alert_records`。
- 1B：迁移 `AlertEngine` 使用 `AlertStore`。
- 1C：创建 `RiskEventStore` / `SummaryStore` 并迁移 `RiskModel`。
- 1D：迁移 `CausalKnowledge` 与 `ConfigVersionManager` 可选接受外部 `conn` / `from_connection()`，消除 `RiskModel.run()` 主事务内的第二条连接。新增 `whyfxpg/tests/test_t1_lock_fix.py` 覆盖并发无锁死场景。

### Phase 2：外部服务端口（LLM + Fetch Source）

#### 2A / T2：LLM Port（已完成，2026-07-29）

- 在 `whyfxpg/ports/llm_port.py` 定义 `LLMPort` 抽象端口：只暴露 `chat_completion(messages, ...) -> str`。
- 在 `whyfxpg/adapters/llm/` 实现：
  - `OpenAICompatAdapter`：复用既有 `LLMClient`，封装 MiniMax / Volcano / Kimi 的 provider 差异与默认模型；默认通过 `get_llm_client()` 单例构造，兼容现有测试 monkeypatch。
  - `InMemoryLLMAdapter`：测试/离线 fake，支持按 prompt 关键字 stub 返回，可断言 `last_prompt`。
- 在 `whyfxpg/services/llm_service.py` 定义 `LLMService`：持有默认 prompt 模板，提供 `extract_entities`、`classify_text`、`summarize`、`risk_reasoning`、`executive_summary` 等语义化方法，负责 JSON 解析与兜底。
- 迁移 `ExtractEngine`、`RiskModel`、`ReportGenerator` 通过 `llm_service` 注入；`LLM_ENABLED=false` 时自动降级为 `InMemoryLLMAdapter`。
- 新增测试：`whyfxpg/tests/test_llm_port.py`、`whyfxpg/tests/test_llm_service.py`。
- 保持 `get_llm_client()` 作为 deprecated 兼容垫片（通过 `OpenAICompatAdapter` 内部使用），不破坏既有调用方。

#### 2B：Source Port（Fetcher 端口化）（已完成，2026-07-29）

- 在 `whyfxpg/ports/source_port.py` 定义 `SourcePort` 与 `FetchedPage` 抽象。
- 在 `whyfxpg/adapters/sources/` 提供 `HttpSourceAdapter`（真实网络）和 `InMemorySourceAdapter`（测试替身）。
- 在 `whyfxpg/core/stores.py` 增加 `MonitorSourceStore` 和 `RawPageStore`。
- 将 `whyfxpg/core/fetcher.py` 改造为 orchestrator，只负责调度 SourcePort 与 Store。
- 测试不再 mock `requests`；通过注入 `InMemorySourceAdapter` 完成。
- 产出：ADR-005 `docs/adr/005-source-port.md`。

#### 2C / T3：ReportBuilder + ReportRenderer Port（已完成，2026-07-29）

- 在 `whyfxpg/services/report_model.py` 定义 `ReportModel` 纯数据对象。
- 在 `whyfxpg/services/report_builder.py` 定义 `ReportBuilder`：读取数据库 + 调用 `LLMService.executive_summary()` + 组装模型。
- 在 `whyfxpg/ports/report_renderer.py` 定义 `ReportRenderer` 端口：`render(model, output_path) -> Path`。
- 在 `whyfxpg/adapters/reports/` 实现：
  - `WordReportRenderer`（python-docx）
  - `ExcelReportRenderer`（openpyxl）
  - `InMemoryReportRenderer`（测试 double）
- 重构 `whyfxpg/core/report_generator.py` 为 orchestrator：注入 builder + renderer，保持 `run()` / `generate_word()` / `generate_excel()` / `fetch_data()` 旧签名不变。
- 新增测试：`whyfxpg/tests/test_report_seams.py`（8 条）。
- 产出：ADR-003 `docs/adr/003-report-renderer-port.md`。

### Phase 3：领域模块深化（Risk + Alert + Causal）

状态：**已完成**（3A、3B、3C 全部落地）。

- 3A：把 `RiskModel` 拆分为 `RiskScorer`（纯评分策略，深模块）和 `RiskEvaluationRunner`（事务编排）。**已完成，2026-07-29。**
  - 新增 `whyfxpg/core/risk_scorer.py`、`whyfxpg/core/risk_evaluation_runner.py`。
  - `RiskModel` 保留为兼容性门面，委托给上述模块。
  - 新增测试 17 条；修复 `history_factor` 公式中 `eval` 缺失 `min` 内置函数的 bug。
  - 产出：ADR-008 `docs/adr/008-risk-scorer-runner.md`。
- 3B：把 `CausalKnowledge` 的宽接口收窄为 `CausalPort.factor(event)` / `CausalPort.explain(event)` / `CausalPort.counterfactual(event, intervention)`。**已完成。**
  - 新增 `CausalGraphStore`（`whyfxpg/core/stores.py`）负责图数据 CRUD。
  - 新增 `CausalReasoning`（`whyfxpg/services/causal_reasoning.py`）纯算法，基于 `GraphView` 协议。
  - 新增 `CausalPort`（`whyfxpg/ports/causal_port.py`）与 `DbCausalAdapter` / `InMemoryCausalAdapter`（`whyfxpg/adapters/causal/`）。
  - `RiskModel` 已改为依赖 `CausalPort`，可注入 `InMemoryCausalAdapter` 测试。
  - 产出：ADR-006 `docs/adr/006-causal-port.md`。
- 3C：引入 `AlertPublisher` 端口，统一 `AlertEngine` 与 `RiskPredictor` 的预警写入。**已完成，2026-07-31。**
  - 新增 `whyfxpg/ports/alert_publisher.py`。
  - 新增 `DbAlertPublisher` / `InMemoryAlertPublisher`（`whyfxpg/adapters/alerts/`）。
  - `AlertEngine` 与 `RiskPredictor` 改为通过 `AlertPublisher` 写入；默认实现仍写 `alert_records`。
  - 新增测试 `test_alert_publisher.py`、`test_risk_predictor.py`。
  - 产出：ADR-009 `docs/adr/009-alert-publisher-port.md`。

### Phase 4：配置与 UI 窄接口化

#### 4A / T5：BigScreenPresenter + DashboardReadModel（已完成，2026-07-29）

- 在 `whyfxpg/webui/read_model.py` 定义 `DashboardReadModel`：无 Streamlit 依赖的数据库查询，返回 pandas DataFrame / dict。
- 在 `whyfxpg/webui/presenters/bigscreen_presenter.py` 定义 `BigScreenPresenter` + `BigScreenViewModel`：把 read model 转换为纯数据视图模型。
- 重构 `whyfxpg/webui/bigscreen.py`：只负责渲染 `BigScreenViewModel`，不再直接查询数据库。
- 改造 `whyfxpg/webui/queries.py`：作为 `DashboardReadModel` 的 Streamlit 缓存包装层，保持 `app.py` 其他页面调用不变。
- 新增测试：`whyfxpg/tests/test_bigscreen_presenter.py`（5 条，不导入 streamlit）。
- 产出：ADR-004 `docs/adr/004-bigscreen-presenter.md`。

- 4B：拆分 `app.py` 到 `whyfxpg/webui/screens/*.py`，`app.py` 只负责导航。✅
- 4E：数据源监控页面（`screens/sources.py`）收口到 `DashboardReadModel`/`queries.get_source_status`，不再直接 `import get_db_connection`。✅
- 4C：抽出 `ReviewService`，把复核表单与 SQL 写入分离。✅
  - 新增 `whyfxpg/services/review_service.py`：`ReviewService` + `ReviewSubmission` / `ReviewRecord` dataclass。
  - `screens/review.py` 只负责表单渲染与历史展示，不再直接 `import get_db_connection`。
  - 新增 `whyfxpg/tests/test_review_service.py`。
  - 产出：ADR-012 `docs/adr/012-review-service.md`。
- 4D：用 dataclass 将 `ConfigLoader` 返回的嵌套 dict 转换为类型化配置对象（已完成，见 T11）。✅
  - 新增 `whyfxpg/config/models.py`、`whyfxpg/config/__init__.py`。
  - `ConfigLoader` 新增 `typed_*` 属性；业务模块逐步迁移。
  - 产出：ADR-010 `docs/adr/010-typed-config-models.md`。

### Phase 5：收尾与 CI

- 5A：全量测试通过，补充集成测试覆盖完整 pipeline。已实施（2026-07-29）：补齐 `RiskEventStore` / `SummaryStore` 单测；`BigScreenPresenter`、`LLMService`、`Fetcher` 已有测试覆盖。
- 5B：为每个重大架构决策补 ADR（已补 ADR-002、003、004、005、006、007、008、009、010、011）。
- 5C：T7 `MigrationRunner` 已实施（2026-07-29）。新增 `whyfxpg/migrations/` 目录、`MigrationRunner`、按版本排序的 `.sql`/`.py` 脚本、`schema_migrations` 版本表；`init_db` 改为兼容 shim。
- 5D：T8 CI 脚本已实施（2026-07-29）。新增 `scripts/check_wal.py`（验证生产库 WAL 模式）和 `scripts/run_tests.py`（统一运行 pytest 与覆盖率）。

## 风险与回滚

- 每次阶段只做一件事，不破坏既有 API 签名（采用可选注入 + 默认回退）。
- 所有变更必须有测试保护；原有 `test_alert_engine.py`、`test_risk_model.py` 必须继续通过。
- 生产 `whyfxpg.db` 不在代码改动范围内；事务 seam 变更只影响代码层，不改动 schema。
