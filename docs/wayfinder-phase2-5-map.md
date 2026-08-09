# WHYfxpg Phase 2–5 Wayfinder Map

## Destination

把 WHYfxpg 从“可运行但浅模块/接口泄漏”的状态推进到“外部依赖可替换、业务逻辑可单元测试、单人可维护”的架构：

- 外部 seam 全部显式化：LLM、网络采集、报告渲染、UI 展示。
- 内部领域 seam 收窄：`RiskScorer`、`CausalPort`、`AlertPublisher` 有清晰接口。
- 修复 Phase 1 遗留的两个高优先级锁库隐患（`ConfigVersionManager` 与 `CausalKnowledge` 独立开连接）。
- 不引入重型新依赖，不重写系统，保持现有 Streamlit 看板 + SQLite 主链路可运行。

## Notes

- 使用 deep-module 词汇：`module / interface / seam / adapter / locality / leverage`。
- 每次阶段只改一个 seam；不破坏既有 API 签名（可选注入 + 默认回退）。
- 测试是接口的一部分：任何新模块必须能通过 in-memory adapter 或内存 DB 测试，不依赖真实网络/LLM。
- 参考既有文件：`docs/architecture-refactor-plan.md`、`docs/adr/001-refactor-not-rewrite.md`。

## Decisions so far

- **ADR-001 重构而非重写**：已选择逐步重构，保留现有可运行系统。
- **T1 P0 锁库隐患已修复**：`ConfigVersionManager`、`CausalKnowledge`、`RiskModel` 均支持复用 `UnitOfWork` 连接；`UnitOfWork.__enter__` 覆盖外部连接的 bug 已修复。新增 `whyfxpg/tests/test_t1_lock_fix.py`。
- **Phase 1 数据访问 seam 完成**：`UnitOfWork` + `AlertStore` / `RiskEventStore` / `SummaryStore` 已落地，`AlertEngine` 与 `RiskModel` 已接入。代码审查报告：`C:\Users\X\AppData\Local\Temp\whyfxpg-phase1-code-review.md`。
- **架构深化评估完成**：4 个优先候选（LLMPort、ReportBuilder、BigScreenPresenter、Source Port）和 2 个候选（CausalKnowledge 拆分、MigrationRunner）已识别。报告：`C:\Users\X\AppData\Local\Temp\whyfxpg-architecture-review.html`。

## Tickets (Frontier & Blocking)

| 编号 | 名称 | 类型 | 阻塞 | 建议 ADR | 状态 |
|---|---|---|---|---|---|
| T1 | 修复 P0 锁库隐患：`ConfigVersionManager` & `CausalKnowledge` 复用 `UnitOfWork` | task | — | 无（缺陷修复） | ✅ 已完成 |
| T2 | 定义 `LLMPort` 与 `LLMService` 拆分 | grilling / prototype | T1 | ADR-002 LLMPort | ✅ 已完成 |
| T3 | 拆分 `ReportGenerator`：`ReportBuilder` + `ReportRenderer` port | task | T2 | ADR-003 ReportRendererPort | ✅ 已完成 |
| T4 | 把网络采集抽象为 `Source` port，`Fetcher` 作为 orchestrator | task | T1 | ADR-005 SourcePort | ✅ 已完成 |
| T5 | 让 `BigScreen` 可测试：`BigScreenPresenter` + `ViewModel` | task | — | ADR-004 BigScreenPresenter | ✅ 已完成 |
| T6 | 拆分 `CausalKnowledge`：`GraphStore` + `Reasoning` | task | T1 | ADR-006 CausalPort | ✅ 已完成 |
| T7 | 评估 `init_db` 改为 `MigrationRunner` | task | T6 | ADR-007 SchemaMigrations | ✅ 已完成 |
| T8 | 测试补齐与 CI 脚本：Store 单测、集成测试、WAL 启用检查 | task | T1–T7 | 无 | ✅ 已完成 |
| T9 | Phase 3A `RiskModel` 拆分：`RiskScorer` + `RiskEvaluationRunner` | task | T1、T2、T6 | ADR-008 RiskScorerRunner | ✅ 已完成 |
| T10 | Phase 3C `AlertPublisher` 端口：统一 AlertEngine 与 RiskPredictor 预警写入 | task | T1、T2、T3 | ADR-009 AlertPublisher | ✅ 已完成 |
|| T11 | Phase 4D 配置类型化：`RiskModelConfig`/`SourcesConfig`/`AlertRulesConfig`/`ExtractRulesConfig` dataclass 封装 | task | T1、T2、T3 | ADR-010 Typed Config | ✅ 已完成 |
|| T12 | Phase 4B WebUI 页面拆分：`app.py` 只负责导航，页面移入 `screens/*.py` | task | T1、T2、T3 | ADR-011 WebUI Screens | ✅ 已完成 |
|| T13 | Phase 4C 抽出 `ReviewService`：人工复核写入从页面中分离 | task | T12 | ADR-012 Review Service | ✅ 已完成 |
|| T14 | 让数据源监控页面（`screens/sources.py`）使用 `DashboardReadModel`，消除页面直接 SQL | task | T12 | （归入 4B） | ✅ 已完成 |
|| -- | **Phase 5** | phase | T1-T14 | -- | 🔲 待启动 |

|---

### T9. Phase 3A `RiskModel` 拆分：`RiskScorer` + `RiskEvaluationRunner`

- **类型**：task（已实施）
- **阻塞**：T1、T2、T6（数据访问 seam、LLM port、Causal port 必须先落地）
- **问题**：`RiskModel` 同时实现评分策略与事务编排，评分逻辑无法脱离数据库测试，接口宽度 ≈ 实现宽度。
- **已实施拆分方案**：
  - `RiskScorer`（`whyfxpg/core/risk_scorer.py`）：纯评分策略，无 DB/网络依赖，输出 `ScoringResult` dataclass。
  - `RiskEvaluationRunner`（`whyfxpg/core/risk_evaluation_runner.py`）：工作流编排，调用 `RiskScorer`、更新数据库、生成 LLM 推理、重建汇总表；支持外部传入 `UnitOfWork`。
  - `RiskModel`（`whyfxpg/core/risk_model.py`）：保留旧签名，作为兼容性门面委托给上述模块。
- **关键决策**：
  - 用 `RiskScorer` 的 `score(event, historical_counts, causal_factor)` seam 把历史统计与因果因子作为输入，而不是让 scorer 自行查库。
  - 修复 `history_factor` 公式 eval 中缺失 `min`/`max` 内置函数的问题（旧代码实际恒为 1.0）。
  - 通过 `RiskModel` facade 兼容既有 `main.py` 和旧测试，避免大面积调用点改动。
- **验收标准**：
  - `test_risk_scorer.py` 11 条通过；`test_risk_evaluation_runner.py` 6 条通过。
  - 旧 `test_risk_model.py`、`test_t1_lock_fix.py`、`test_causal_seams.py` 继续通过。
  - 全量 pytest 108 条通过。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`whyfxpg/core/risk_scorer.py`、`whyfxpg/core/risk_evaluation_runner.py`、`whyfxpg/tests/test_risk_scorer.py`、`whyfxpg/tests/test_risk_evaluation_runner.py`。
  - 修改：`whyfxpg/core/risk_model.py`（重构为 facade）。
- **产出**：ADR-008 `docs/adr/008-risk-scorer-runner.md`。

---

### T10. Phase 3C `AlertPublisher` 端口：统一 AlertEngine 与 RiskPredictor 预警写入

- **类型**：task（已实施）
- **阻塞**：T1、T2、T3（数据访问 seam、已有 AlertStore、配置加载）
- **问题**：`AlertEngine` 与 `RiskPredictor` 各自写入 `alert_records`，去重/插入逻辑重复；`RiskPredictor` 直接执行 SQL。
- **已实施拆分方案**：
  - `AlertPublisher`（`whyfxpg/ports/alert_publisher.py`）：单一 `publish(alert)` 端口。
  - `DbAlertPublisher`（`whyfxpg/adapters/alerts/db_alert_publisher.py`）：基于 `AlertStore` 实现去重与插入。
  - `InMemoryAlertPublisher`（`whyfxpg/adapters/alerts/in_memory_alert_publisher.py`）：测试 double。
  - `AlertEngine` 新增 `publisher_factory` 参数，规则方法通过 publisher 发布预警。
  - `RiskPredictor.write_predictive_alerts` 新增 `publisher`/`uow` 参数，默认使用 `DbAlertPublisher`。
- **关键决策**：
  - 保持 `AlertEngine` 与 `RiskPredictor` 默认入口签名不变；新增参数均为可选注入。
  - 去重逻辑仍由 `AlertStore.find_existing` 提供，publisher 只负责“是否发布”的 seam 抽象。
- **验收标准**：
  - `test_alert_publisher.py` 3 条通过。
  - `test_alert_engine.py` 新增 seams 测试通过。
  - `test_risk_predictor.py` 3 条通过。
  - 全量 pytest 通过。
- **状态**：✅ 已完成（2026-07-31）。
- **改动文件**：
  - 新增：`whyfxpg/ports/alert_publisher.py`、`whyfxpg/adapters/alerts/__init__.py`、`whyfxpg/adapters/alerts/db_alert_publisher.py`、`whyfxpg/adapters/alerts/in_memory_alert_publisher.py`、`whyfxpg/tests/test_alert_publisher.py`、`whyfxpg/tests/test_risk_predictor.py`。
  - 修改：`whyfxpg/core/alert_engine.py`、`whyfxpg/core/risk_predictor.py`、`whyfxpg/tests/test_alert_engine.py`。
- **产出**：ADR-009 `docs/adr/009-alert-publisher-port.md`。

---

### T11. Phase 4D 配置类型化

- **类型**：task（已实施）
- **阻塞**：T1–T10（配置加载、各业务 seam 必须先落地）
- **问题**：`ConfigLoader` 长期返回嵌套 dict，业务模块中 `cfg.get(...)` 链式调用无类型提示，字段缺失时默认行为分散。
- **已实施方案**：
  - 新增 `whyfxpg/config/models.py`，基于标准库 `dataclasses` 定义 `RiskModelConfig`、`SourcesConfig`、`AlertRulesConfig`、`ExtractRulesConfig`、`KeywordsConfig` 及其嵌套子模型。
  - `ConfigLoader` 保留原有 dict 属性，新增 `typed_risk_model`、`typed_sources`、`typed_alert_rules`、`typed_extract_rules`、`typed_keywords`。
  - `RiskScorer`、`RiskEvaluationRunner`、`RiskModel`、`AlertEngine`、`Fetcher`、`ExtractEngine` 逐步迁移到类型化配置。
  - `SourceConfig.to_dict()` 作为与旧 dict 接口适配器的桥接。
- **关键决策**：
  - 不引入 Pydantic，避免新增依赖。
  - `ExtractRule` 将 YAML 键 `field` 映射到属性 `field_name`，避免与 `dataclasses.field` 冲突。
- **验收标准**：
  - `whyfxpg/tests/test_config_models.py` 通过。
  - 全量 pytest 123 条通过。
- **状态**：✅ 已完成（2026-07-31）。
- **改动文件**：
  - 新增：`whyfxpg/config/models.py`、`whyfxpg/config/__init__.py`、`whyfxpg/tests/test_config_models.py`。
  - 修改：`whyfxpg/core/config_loader.py`、`whyfxpg/core/risk_scorer.py`、`whyfxpg/core/risk_evaluation_runner.py`、`whyfxpg/core/risk_model.py`、`whyfxpg/core/alert_engine.py`、`whyfxpg/core/fetcher.py`、`whyfxpg/core/extract_engine.py`。
- **产出**：ADR-010 `docs/adr/010-typed-config-models.md`。

---

### T1. 修复 P0 锁库隐患：`ConfigVersionManager` & `CausalKnowledge` 复用 `UnitOfWork`

- **类型**：task（AFK，可自动执行）
- **阻塞**：无
- **问题**：`RiskModel.run()` 的主事务内，`get_current_config_version()` 会创建新的 `ConfigVersionManager` 并打开第二条连接；`CausalKnowledge` 的 `get_causal_factor()` 也会反复独立连接。这在生产环境仍可能触发 `database is locked`。
- **验收标准**：
  1. `ConfigVersionManager` 支持传入已有 `sqlite3.Connection` 或 `UnitOfWork`。
  2. `CausalKnowledge` 支持 `from_connection(conn)` 或传入 `UnitOfWork`。
  3. `RiskModel.run()` 全程只使用一个连接。
  4. 现有 pytest 全量通过（除既有的 `test_extract_event_from_page` 预期不符外），新增并发写入不锁死测试。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - `whyfxpg/core/stores.py`：修复 `UnitOfWork.__enter__` 在 `from_connection` 场景下会覆盖外部连接的 bug。
  - `whyfxpg/core/config_version.py`：`ConfigVersionManager` 支持 `conn`/`from_connection`。
  - `whyfxpg/core/causal_knowledge.py`：`CausalKnowledge` 支持 `conn`/`from_connection`。
  - `whyfxpg/core/risk_model.py`：`run()` 内使用 `from_connection` 复用 `UnitOfWork` 连接。
  - `whyfxpg/tests/test_t1_lock_fix.py`：新增 4 条 T1 测试。
- **产出**：代码改动 + 更新 `docs/architecture-refactor-plan.md` 中 Phase 1 相关描述。

---

### T2. 定义 `LLMPort` 与 `LLMService` 拆分

- **类型**：prototype（已实施）
- **阻塞**：T1
- **问题**：全局单例 `get_llm_client()` 混合 provider 配置、HTTP 调用、提示模板、JSON 解析；被 `ExtractEngine`、`RiskModel`、`ReportGenerator` 直接引用。
- **已决策**：
  1. `LLMPort` 最小接口 = `chat_completion(messages, model, temperature, max_tokens, **kwargs) -> str`。
  2. 语义化方法（`extract_entities`、`classify_text`、`summarize`、`risk_reasoning`、`executive_summary`）放入 `LLMService`。
  3. 提示模板归 `LLMService`；调用方允许注入 `prompt_template`；adapter 只负责协议转换。
  4. 保留 `get_llm_client()` 作为 deprecated 兼容垫片（`OpenAICompatAdapter` 内部使用）。
  5. 默认生产 adapter 读取 `.env` 中的 `DEFAULT_LLM_PROVIDER=minimax`；`LLM_ENABLED=false` 时自动降级为 `InMemoryLLMAdapter`。
- **验收标准**：
  1. `LLMPort` 抽象接口可被子类化/测试。
  2. `OpenAICompatAdapter` 可注入 fake `LLMClient` 或走全局单例。
  3. `InMemoryLLMAdapter` 支持按 prompt 关键字 stub 返回并记录 `last_prompt`。
  4. `LLMService` 语义化方法全部可通过 `InMemoryLLMAdapter` 测试。
  5. 现有 `test_extract_engine.py`、`test_risk_model.py` 继续通过。
  6. 新增 `test_llm_port.py`、`test_llm_service.py` 并通过。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`whyfxpg/ports/llm_port.py`、`whyfxpg/adapters/llm/openai_compat_adapter.py`、`whyfxpg/adapters/llm/in_memory_adapter.py`、`whyfxpg/services/llm_service.py`、`whyfxpg/tests/test_llm_port.py`、`whyfxpg/tests/test_llm_service.py`。
  - 修改：`whyfxpg/core/extract_engine.py`、`whyfxpg/core/risk_model.py`、`whyfxpg/core/report_generator.py`、`whyfxpg/tests/conftest.py`（`DummyLLMClient` 新增 `chat_completion`）。
- **产出**：ADR-002 `docs/adr/002-llm-port.md`（待补）。

---

### T3. 拆分 `ReportGenerator`：`ReportBuilder` + `ReportRenderer` port

- **类型**：task（已实施）
- **阻塞**：T2
- **问题**：当前 `ReportGenerator` 同时负责数据查询、LLM 摘要、Word 排版、Excel 导出、输出目录管理，接口宽度 ≈ 实现宽度。
- **已实施拆分方案**：
  - `ReportModel`：纯数据对象，在 builder 与 renderer 之间传递。
  - `ReportBuilder`（`whyfxpg/services/report_builder.py`）：读取数据库，调用 `LLMService.executive_summary()`，组装 `ReportModel`。
  - `ReportRenderer` port（`whyfxpg/ports/report_renderer.py`）：`render(model, output_path) -> Path`。
  - `WordReportRenderer` / `ExcelReportRenderer` / `InMemoryReportRenderer`（`whyfxpg/adapters/reports/`）。
  - `ReportGenerator` 保留为 orchestrator，兼容旧 `run()` / `generate_word()` / `generate_excel()` / `fetch_data()` 签名。
- **验收标准**：
  1. `ReportBuilder` 可脱离 Word/Excel 库测试。
  2. `InMemoryReportRenderer` 可记录渲染调用，不依赖文件系统。
  3. Word/Excel 渲染可通过文件 smoke test 验证。
  4. `main.py` / `webui/app.py` 调用方式不变。
  5. 新增 `test_report_seams.py` 并通过。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`whyfxpg/services/report_model.py`、`whyfxpg/services/report_builder.py`、`whyfxpg/ports/report_renderer.py`、`whyfxpg/adapters/reports/*.py`、`whyfxpg/tests/test_report_seams.py`。
  - 修改：`whyfxpg/core/report_generator.py`。
- **产出**：ADR-003 `docs/adr/003-report-renderer-port.md`。

---

### T4. 把网络采集抽象为 `Source` port，`Fetcher` 作为 orchestrator

- **类型**：task（已实施）
- **阻塞**：T1（已解决）
- **问题**：`Fetcher` 直接调用 `requests`，测试必须 mock 网络；采集策略与 HTTP 细节混在同一文件中。
- **已实施拆分方案**：
  - `SourcePort` + `FetchedPage`（`whyfxpg/ports/source_port.py`）：最小接口 `fetch(source_id, cfg) -> FetchedPage`。
  - `HttpSourceAdapter`（`whyfxpg/adapters/sources/http_source_adapter.py`）：基于 `requests` + 超时/错误处理。
  - `InMemorySourceAdapter`（`whyfxpg/adapters/sources/in_memory_source_adapter.py`）：测试 double，支持 fixture 或回调。
  - `MonitorSourceStore` + `RawPageStore`（`whyfxpg/core/stores.py`）：负责 `monitor_sources` / `raw_pages` / `crawl_logs` 写入。
  - `Fetcher`（`whyfxpg/core/fetcher.py`）：只负责读取配置、调度 SourcePort、调用 Store。
- **验收标准**：`whyfxpg/tests/test_fetcher.py` 8 条通过，无需 mock `requests`；原有 70 条全量通过。
- **产出**：`whyfxpg/ports/source_port.py` + adapters + store + `docs/adr/005-source-port.md`。
- **后续影响**：T6 拆分时 `CausalPort` 可复用同一 seam 思路。

---

### T5. 让 `BigScreen` 可测试：`BigScreenPresenter` + `ViewModel`

- **类型**：task（已实施）
- **阻塞**：无
- **问题**：`render_bigscreen` 认知复杂度高，同时做数据查询、转换、布局、图表渲染，无法脱离 Streamlit 测试。
- **已实施拆分方案**：
  - `DashboardReadModel`（`whyfxpg/webui/read_model.py`）：无 Streamlit 依赖的数据库查询，返回 pandas DataFrame / dict。
  - `BigScreenPresenter` + `BigScreenViewModel`（`whyfxpg/webui/presenters/bigscreen_presenter.py`）：把原始数据转为视图模型。
  - `render_bigscreen`：只接收 `BigScreenViewModel` 并调用 Streamlit 组件；缺省时才自行组装 presenter。
  - `queries.py`：改造为 `DashboardReadModel` 的 Streamlit 缓存包装层，保持 `app.py` 其他页面调用不变。
- **验收标准**：
  1. 新增 `test_bigscreen_presenter.py` 不 import streamlit。
  2. 通过 fake `DashboardReadModel` 可断言 presenter 输出字段。
  3. 大屏展示效果不变。
  4. 全量 pytest 通过。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`whyfxpg/webui/read_model.py`、`whyfxpg/webui/presenters/bigscreen_presenter.py`、`whyfxpg/tests/test_bigscreen_presenter.py`。
  - 修改：`whyfxpg/webui/bigscreen.py`、`whyfxpg/webui/queries.py`。
- **产出**：ADR-005 `docs/adr/004-bigscreen-presenter.md`。

---

### T6. 拆分 `CausalKnowledge`：`GraphStore` + `Reasoning`

- **类型**：task（已实施）
- **阻塞**：T1（与 `RiskModel` 共用连接）
- **问题**：`CausalKnowledge` 将 schema 管理、节点/边 CRUD、因果传播、反事实推理、解释生成全部耦合在一个 facade 中。
- **已实施拆分方案**：
  - `CausalGraphStore`（`whyfxpg/core/stores.py`）：负责 `causal_nodes` / `causal_edges` / `causal_paths` 的 CRUD，接受 `UnitOfWork`。
  - `CausalReasoning`（`whyfxpg/services/causal_reasoning.py`）：纯算法模块，基于 `GraphView` 协议实现传播、反事实、解释生成。
  - `CausalPort`（`whyfxpg/ports/causal_port.py`）：面向 `RiskModel` 的最小接口：`factor(event)` / `explain(event)` / `counterfactual(event, intervention)`。
  - `DbCausalAdapter` / `InMemoryCausalAdapter`（`whyfxpg/adapters/causal/`）：生产与内存适配器。
  - `CausalKnowledge` 保留为 facade，旧接口不变，内部委托给上述模块。
- **验收标准**：
  - `CausalReasoning` 可在内存数据上测试；
  - `CausalPort` 默认实现使用 `CausalGraphStore` + `CausalReasoning`；
  - `RiskModel` 可注入 `InMemoryCausalAdapter` 完成评分；
  - 全量 pytest 通过。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`whyfxpg/services/causal_reasoning.py`、`whyfxpg/ports/causal_port.py`、`whyfxpg/adapters/causal/db_causal_adapter.py`、`whyfxpg/adapters/causal/in_memory_causal_adapter.py`、`whyfxpg/adapters/causal/__init__.py`、`whyfxpg/tests/test_causal_seams.py`。
  - 修改：`whyfxpg/core/stores.py`（新增 `CausalGraphStore`）、`whyfxpg/core/causal_knowledge.py`（facade 化）、`whyfxpg/core/risk_model.py`（改为依赖 `CausalPort`）。
- **产出**：`docs/adr/006-causal-port.md`。

---

### T7. 评估 `init_db` 改为 `MigrationRunner`

- **类型**：task（AFK）
- **阻塞**：T6（先稳定因果 schema，再统一 schema 管理）
- **问题**：`init_db` 222 行，所有 `CREATE TABLE` 写在一个函数；列变更靠 `try/except` 静默吞错。
- **已实施方案**：
  - 新增 `whyfxpg/migrations/` 目录：`001_init_schema.sql`（业务表/索引）、`002_causal_graph.sql`（因果图表/索引）、`003_add_causal_factor.py`（向后兼容补列）。
  - 新增 `MigrationRunner`（`whyfxpg/migrations/runner.py`）：维护 `schema_migrations` 表，按版本号顺序执行未应用的 migration；支持 `.sql` 与 `.py`。
  - `init_db()` 保留为兼容 shim，内部调用 `MigrationRunner`；新代码建议直接使用 `MigrationRunner(conn).run()`。
  - `CausalGraphStore.ensure_schema()` 改为通过 `MigrationRunner` 统一创建，避免重复 DDL。
- **验收标准**：新增字段时只需添加 migration 文件，不改动 `init_db` 主体；测试可从头重建 schema；全量 pytest 通过。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`whyfxpg/migrations/runner.py`、`whyfxpg/migrations/__init__.py`、`whyfxpg/migrations/001_init_schema.sql`、`whyfxpg/migrations/002_causal_graph.sql`、`whyfxpg/migrations/003_add_causal_factor.py`、`whyfxpg/tests/test_migration_runner.py`。
  - 修改：`whyfxpg/core/db.py`、`whyfxpg/core/stores.py`（`CausalGraphStore.ensure_schema` 委托 MigrationRunner）、`scripts/enable_wal.py`。
- **产出**：`docs/adr/007-schema-migrations.md`。

---

### T8. 测试补齐与 CI 脚本

- **类型**：task（AFK）
- **阻塞**：T1–T4（先完成模块拆分，再补测试）
- **任务**：
  1. 补充 `RiskEventStore` / `SummaryStore` 单测。
  2. 补充 `BigScreenPresenter` 单元测试。
  3. 补充 `LLMService` 使用 `InMemoryLLMAdapter` 的测试。
  4. 补充 `Fetcher` 使用 `InMemorySourceAdapter` 的集成测试。
  5. 提供 `scripts/check_wal.py` 验证生产库已启用 WAL。
  6. 提供 `scripts/run_tests.py` 统一运行 pytest 与 schema 检查。
- **验收标准**：pytest 全量通过；新增测试覆盖率 > 60%（在现有基础上）。
- **状态**：✅ 已完成（2026-07-29）。
- **改动文件**：
  - 新增：`scripts/check_wal.py`、`scripts/run_tests.py`。
  - 修改：`whyfxpg/tests/test_stores.py`（补充 `RiskEventStore` / `SummaryStore` 单测；引入 `_insert_risk_event` helper）。
- **说明**：`BigScreenPresenter`、`LLMService`、`Fetcher` 已有对应测试覆盖，本次未新增文件，仅补齐缺失的 Store 单测。

## Not yet specified

以下区域已模糊看到，但还不能精确 ticket，等前沿推进后毕业为具体 ticket：

- **WebUI 页面拆分**：`app.py` 421 行，是否拆为 `pages/` 目录，让 `app.py` 只保留导航？
- **ReviewService**：人工复核表单与 SQL 写入是否抽成独立服务？
- **数据血缘/可观测性**：是否需要为 pipeline 增加运行日志或指标？

## Out of scope

- **重写系统**：保留现有 SQLite + Streamlit + YAML 配置的主链路。
- **引入新数据库/搜索引擎**：不迁移到 Postgres/Elasticsearch。
- **微服务拆分**：保持单进程/单仓库。
- **引入第三方商业 BI 工具**：大屏使用原生 Streamlit 组件；不引入 Superset/Metabase/DataV 作为运行时依赖。
- **多语言前端**：不引入 React/Vue 前端。
- **实时流处理**：不引入 Kafka/Flink。

### T14. 数据源监控页面收口到 `DashboardReadModel`

- **类型**：task（已实施）
- **阻塞**：T12（WebUI 页面拆分必须先落地）
- **问题**：`whyfxpg/webui/screens/sources.py` 仍直接 `from whyfxpg.core.db import get_db_connection` 并执行 `SELECT * FROM monitor_sources ...`，让页面层持有连接细节，难以在内存 DB 中测试。
- **已实施方案**：
  - 扩展 `DashboardReadModel.get_source_status()` 返回 `monitor_sources` 全部列。
  - `screens/sources.py` 改为从 `whyfxpg.webui.queries import get_source_status` 读取数据，仅负责列名重命名与刷新按钮渲染。
  - 新增 `whyfxpg/tests/test_read_model.py` 覆盖 `get_source_status`（含空表场景）。
  - 在 `whyfxpg/tests/test_webui_screens.py` 增加断言：所有页面模块源码中不再出现 `get_db_connection`。
- **验收标准**：
  - `screens/sources.py` 源码中无 `get_db_connection` 字符串。
  - 全量 pytest 通过。
- **状态**：✅ 已完成。
- **改动文件**：
  - 修改：`whyfxpg/webui/read_model.py`、`whyfxpg/webui/screens/sources.py`、`whyfxpg/tests/test_webui_screens.py`。
  - 新增：`whyfxpg/tests/test_read_model.py`。

---

## 下一步行动

1. ✅ T1 已完成。
2. ✅ T2（LLMPort）已完成；补 ADR-002。
3. ✅ T3（ReportBuilder + ReportRenderer Port）已完成；补 ADR-003。
4. ✅ T4（Source Port）已完成；ADR-005 已补。
5. ✅ T5（BigScreenPresenter）已完成；ADR-004 已补。
6. ✅ T6（CausalKnowledge 拆分）已完成；ADR-006 已补。
7. ✅ T7（MigrationRunner）已完成；ADR-007 已补。
8. ✅ T8 已完成。
9. ✅ T9 / Phase 3A `RiskModel` 拆分已完成。
10. ✅ T10 / Phase 3C `AlertPublisher` 端口已完成。
11. ✅ T11 / Phase 4D 配置类型化已完成。
12. ✅ T12 / Phase 4B WebUI 页面拆分已完成；T14 已补充，所有页面无直接 SQL。
13. ✅ T13 / Phase 4C `ReviewService` 已完成。
14. 建议下一步：进入 Phase 5 收尾/CI（如修复 `scripts/run_tests.py`、补充集成测试、生成架构审计报告），或基于 Matt Pocock 深模块词汇做一次整体架构审计。

---

## Phase 6 (v2) — Multi-domain quality risk assessment

See the new Wayfinder map at `.scratch/wayfinder/map.md` and the research notes at `.scratch/wayfinder/research/`. Phase 6 builds on T1–T14 and targets the user's concerns around CRUD maintainability, rule engine maintenance, end-to-end pipeline visibility, source monitoring, and rich dashboards.

