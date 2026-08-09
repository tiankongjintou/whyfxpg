# ADR-008：拆分 `RiskModel` 为 `RiskScorer` + `RiskEvaluationRunner`

## 状态

已接受（Accepted），2026-07-29。

## 背景

`whyfxpg/core/risk_model.py` 将两类完全不同的职责耦合在一个类中：

1. **评分策略**：严重度/概率/国别/产品/历史/证据等查表、公式计算、风险等级映射。
2. **事务编排**：打开 `UnitOfWork`、查询待评分事件、获取历史统计、调用因果端口、更新数据库、生成 LLM 推理、重建汇总表。

这导致：

- **评分策略无法脱离数据库测试**：计算一个 `total_score` 必须构造完整事件并依赖 `RiskEventStore`。
- **历史统计与评分逻辑纠缠**：Runner 负责查历史，`RiskModel` 负责算概率， seams 不清晰。
- **接口宽度 ≈ 实现宽度**：`RiskModel` 同时暴露 `severity_to_score`、`probability_to_score`、`evaluate_event`、`run`、`add_risk_reasoning` 等方法，调用方难以判断应使用哪一层。

## 决策

1. 拆分出 **`RiskScorer`**（`whyfxpg/core/risk_scorer.py`）：
   - **纯评分策略模块**，无数据库/网络依赖。
   - 接收 `model_cfg`、`event`、`historical_counts`、`causal_factor`。
   - 输出 `ScoringResult`（dataclass），包含 ss_score、ps_score、total_score、rs_level 等全部评分结果。
   - 内部封装所有查表逻辑、公式解析与阈值映射。

2. 拆分出 **`RiskEvaluationRunner`**（`whyfxpg/core/risk_evaluation_runner.py`）：
   - **工作流编排模块**，负责 `fetch_pending → score → update_scores → reason → rebuild_summaries`。
   - 依赖 `UnitOfWork`、`RiskEventStore`、`SummaryStore` 等数据访问 seam。
   - 通过 `CausalPort` 注入因果因子（默认 `DbCausalAdapter`，测试可替换）。
   - 通过 `LLMService` 注入推理服务（默认 `LLMService()`，测试可注入 `FixedLLMPort`）。
   - 支持外部传入 `UnitOfWork`，复用同一连接，避免锁库。

3. **`RiskModel` 改为兼容性门面（facade）**：
   - 保留既有构造签名 `RiskModel(config_dir=None, db_path=None, llm_service=None, causal_port=None)`。
   - 保留 `severity_to_score`、`calculate_total_score`、`map_to_risk_level`、`evaluate_event`、`run` 等旧方法。
   - 所有方法委托给 `RiskScorer` 或 `RiskEvaluationRunner`。
   - 旧调用方（`main.py`、既有测试）无需修改即可继续工作。

4. **明确两个 seams**：
   - **Policy seam**：`RiskScorer.score(event, historical_counts, causal_factor)`。
   - **Orchestration seam**：`RiskEvaluationRunner.run(uow=None)`。

## 决策依据

- **Deep module**：`RiskScorer` 内部复杂（公式 eval、多级查表、阈值映射），但对外只暴露 `score()`；`RiskEvaluationRunner` 内部复杂（多 store 协调），对外只暴露 `run()`。
- **Locality**：评分规则变更只改 `risk_scorer.py`；工作流变更只改 `risk_evaluation_runner.py`。
- **Test surface**：`RiskScorer` 可用纯内存 dict 测试；`RiskEvaluationRunner` 可用临时 SQLite + fake adapter 测试，不依赖真实 LLM。
- **兼容性**：`RiskModel` facade 避免在单次重构中改动所有调用方，降低单人维护风险。
- **历史因子公式 bug 顺带修复**：旧实现因 `eval` 缺少 `min` 内置函数导致 `history_factor` 始终返回 `1.0`；新实现显式提供 `min`/`max` 安全内置，使公式生效。

## 影响

- 新增 `whyfxpg/tests/test_risk_scorer.py`（11 条）与 `whyfxpg/tests/test_risk_evaluation_runner.py`（6 条）。
- 全量 pytest 从 91 条增加到 **108 条**。
- `RiskModel` 不再承担核心实现，旧入口行为不变但标记为 facade；新代码优先使用 `RiskScorer`/`RiskEvaluationRunner`。
- 后续若需调整评分规则（如新增因子、替换阈值），只改 `RiskScorer`。
- 后续若需支持批量评分、异步评分、消息队列，只改 `RiskEvaluationRunner`。

## 相关文件

- `whyfxpg/core/risk_scorer.py`（新增）
- `whyfxpg/core/risk_evaluation_runner.py`（新增）
- `whyfxpg/core/risk_model.py`（重构为 facade）
- `whyfxpg/tests/test_risk_scorer.py`（新增）
- `whyfxpg/tests/test_risk_evaluation_runner.py`（新增）
- `docs/wayfinder-phase2-5-map.md`
- `docs/architecture-refactor-plan.md`
