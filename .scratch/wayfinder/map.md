# Wayfinder Map: WHYfxpg v2 (Multi-domain Quality Risk Assessment)

> 标签：`wayfinder:map`  
> 状态：charting complete — frontier tickets ready for execution  
> 前置地图：`docs/wayfinder-phase2-5-map.md`（T1–T14 已完成）

---

## Destination

把 WHYfxpg 从“海关进口机电产品专用风险看板”推进为 **可跨行业、可配置、可维护、可观测的通用质量风险评估平台**：

- 所有领域对象（数据源、规则、模型、维度、分类法）都有可维护的 CRUD/版本/审计入口；
- 风险评估规则由统一 `RuleEngine` 管理，支持沙盒、解释、版本回归与 A/B 测试；
- 端到端信息管道（采集 → 过滤 → 提取 → 结构化 → 提炼 → 评估 → 归档）被显式建模，可监控、可追踪、可归档；
- 数据源监控不再只是“维护来源列表”，而是提供健康度、新鲜度、延迟、覆盖率、血缘与告警；
- 风险态势大屏从单一页面变成可配置 widget + 模板 + 钻取 + 导出的富看板；
- 架构保持 seam-first（Port + Adapter + 两个实现），让单开发者也能安全扩展新行业域。

---

## Notes

- 使用 Matt Pocock 深模块词汇：`module / interface / seam / adapter / port / depth / locality / leverage`。
- 每次阶段只打开一个 seam；不破坏既有 API 签名（可选注入 + 默认回退）。
- 测试是接口的一部分：每个新 Port 必须同时落地一个生产适配器 + 一个 InMemory 测试替身，并附带测试。
- 参考研究文档：
  - `CONTEXT.md` — 领域术语与边界规则
  - `.scratch/wayfinder/research/01-domain-and-modules.md` — v2 目标模块与 seam 分层
  - `.scratch/wayfinder/research/02-current-pipeline.md` — 当前数据流审计与显式缺口
  - `.scratch/wayfinder/research/03-capabilities-design.md` — Admin、RuleEngine、Monitor、Dashboard、Multi-domain 设计
- 上一个 Wayfinder 地图 `docs/wayfinder-phase2-5-map.md` 的 T1–T14 已闭环，当前地图从 T15 开始。

---

## Decisions so far (carried forward + new)

- **ADR-001 重构而非重写**：继续沿用，保留现有 SQLite + Streamlit + YAML 主链路可运行。
- **T1–T14 已完成**：`LLMPort`、`SourcePort`、`ReportRenderer`、`CausalPort`、`AlertPublisher`、`BigScreenPresenter`、`MigrationRunner`、`RiskScorer/Runner`、`AlertPublisher`、`Typed Config`、`WebUI screens split`、`ReviewService`、`Sources read model` 已落地。
- **T14 之后架构审计结论**：`core/stores.py` 仍是最大浅模块（746 LOC / 82 公开成员），`webui/screens/causal.py` 仍是最后一个 UI 层 DB 泄漏，`adapters/llm/openai_compat_adapter.py` 仍回退到旧 `core.llm_client`，`FeedbackLearner` 闭环未闭合，`ExcelReportRenderer` 仍直接查 DB。
- **v2 新决策 D1**：配置以 YAML 为主存储，但统一通过 `ConfigStorePort` 读写，使 Admin UI 未来可切换 `DbConfigStoreAdapter` 而不改业务代码。
- **v2 新决策 D2**：规则引擎查询计划优先于 SQL 拼接；`RuleCompilerPort` 负责把 YAML DSL 翻译成 plan，再由不同 adapter 执行（SQLite / Pandas / LLM），保证可解释和可测试。
- **v2 新决策 D3**：监控指标从 `crawl_logs` 派生，不引入独立时序数据库；未来换 Prometheus 只改 `SourceHealthPort` adapter。
- **v2 新决策 D4**：大屏保持 60 秒轮询，不引入 WebSocket/消息队列；实时 seam 留给未来 `DashboardDataPort` adapter。
- **v2 新决策 D5**：多行业扩展通过 `DomainProfile` + `TaxonomyPort` / `DimensionPort` 切换，而不是多实例服务；保持单仓库、单进程。
- **v2 新决策 D6**：新模块必须先写 Port + 两个适配器，再写业务逻辑；单元测试必须能不依赖真实网络/LLM/DB 通过。
- **ADR-022 基础可观测性**：通过 `TelemetryPort` 记录 pipeline 运行耗时、adapter 调用计数、健康快照，默认 `NullTelemetryPort`，测试使用 `InMemoryTelemetryAdapter`。
- **ADR-023 多行业域模板**：新增化工、食品、玩具、汽车四个行业域 YAML 模板，验证 `DomainRegistryService` 可自动发现并切换。

---

## Tickets (Frontier & Blocking)

||| # | 名称 | 类型 | 阻塞 | 建议 ADR | 状态 |
|---|---|---|------|------|------|----------|------|
|||| T15 | Admin CRUD seam：`ConfigurationAdminService` + `ConfigStorePort` | task | — | ADR-013 | ✅ 已完成 |
|||| T16 | RuleEngine seam：`RuleEngine` + `RuleCompilerPort` + `RuleRepositoryPort` | task | T15 | ADR-014 | ✅ 已完成 |
|||| T17 | SourceMonitor seam：`SourceMonitorService` + `SourceHealthPort` | task | T15 | ADR-015 | ✅ 已完成 |
|||| T18 | Dashboard v2 seam：`DashboardBuilderService` + `DashboardDataPort` + `DashboardExportPort` | task | T15 | ADR-016 | ✅ 已完成 |
|||||| T19 | Multi-domain seam：`DomainProfile` + `DomainRegistryService` + `TaxonomyPort` + `DimensionPort` | task | T15、T16 | ADR-017 | ✅ 已完成 |
||||| T20 | Pipeline & Archive seam：`InformationPipeline` + `PipelineOrchestrator` + `ArchivePort` + 审计/血缘 | task | T15–T18 | ADR-018 | ✅ 已完成 |
||||| T21 | Close remaining Phase 2–5 leaks：split `core/stores.py`, fix `screens/causal.py`, refactor LLM adapter, close FeedbackLearner loop, tighten Excel renderer | task | T15 | ADR-019 | ✅ 已完成 |
||||| T22 | End-to-end v2 integration test + documentation | task | T15–T21 | ADR-020 | ✅ completed |
||||| T23 | Close remaining webui screen leaks | task | T21 | ADR-021 | ✅ completed |
||||| T24 | Streamlit UI restart and smoke verification | task | T23 | — | ✅ completed |
|||| T25 | Check redundant archive port files (`archive_port.py` / `archive.py`) | task | T24 | — | ✅ completed |
|||| T26 | Install `pytest-cov` and enable coverage by default in `run_tests.py` | task | T24 | — | ✅ completed |
|||| T27 | Basic telemetry: pipeline duration, adapter call counts, health snapshots | task | T24 | ADR-022 | ✅ completed |
|||| T28 | Add new industry domain templates (chemical / food / toy / automotive) | task | T27 | ADR-023 | ✅ completed |

---

## Not yet specified

- 大屏是否需要深色/会议室/移动端多套模板；
- 是否引入外部身份认证（当前单用户 Streamlit）；
- 是否需要报告自动邮件/钉钉推送；
- 生产数据库是否需要自动备份脚本（ beyond WAL）。

---

## Out of scope

- 重写系统或迁移到 Postgres/Elasticsearch/ClickHouse；
- 微服务拆分或多节点部署；
- 引入 React/Vue 等独立前端；
- 引入 Kafka/Flink 等实时流处理；
- 引入第三方商业 BI（Superset/Metabase/DataV）作为运行时依赖；
- 多租户/多组织隔离（保持单用户或单组织）。

---

## Next action

1. T15–T28 全部完成；v2 seam-first 架构基线完全闭合，基础可观测性与多行业域模板已落地。
2. 当前无 pending frontier ticket；后续可选方向待业务优先级确定：
   - 为新增行业域补充示例数据源与监控指标；
   - 将可观测性数据接入大屏或 Admin 页面；
   - 清理误写目录 `D:/Seafile/SeaHome/TempProjects/WHHYfxpg`（需显式授权）；
   - 启动下一轮架构审计或 Wayfinder 规划。

## phase1b（2026-08-11 起）

新批次：技术债清理与多租户运营闭环。

- P1b-01 账户管理 API（注册/Key 轮换/禁用）— **in-progress**（reasonix-agent）
- 待 chart：stores Repository 统一、评分归一化 0-100、配置迁移 PG

## Notes

- 当前后台 Web UI 进程：`proc_f2a5c187e1b3`（PID 313688），监听 http://localhost:8501。
- 全量测试最新计数：**239 passed, 1 skipped, 8 warnings, 79% coverage**；架构检查零 warning。
- `pytest-cov` 已安装，`scripts/run_tests.py` 默认启用覆盖率；仍可用 `--no-cov` 绕过。
- 如需测试某个页面，访问 `http://localhost:8501/?page=...`（具体 page 名称由 `webui/screens/__init__.py` 的 PAGES 映射决定）。
