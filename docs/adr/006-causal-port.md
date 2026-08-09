# ADR-006：拆分 `CausalKnowledge` 为 `CausalGraphStore` + `CausalReasoning` + `CausalPort`

## 状态

已接受（Accepted），2026-07-29。

## 背景

`whyfxpg/core/causal_knowledge.py`  originally 将以下职责全部放在一个类中：

1. 因果图 schema 创建（`causal_nodes` / `causal_edges` / `causal_paths` 表）。
2. 节点/边的 CRUD 与查询（数据库操作）。
3. 因果传播、反事实推理、解释生成的算法逻辑。
4. 面向 `RiskModel` 与 WebUI 的业务 facade。

这导致：

- **算法无法脱离数据库测试**：任何因果推理测试都必须创建 SQLite 表并写入数据。
- **图存储细节泄漏到 RiskModel**：`RiskModel` 直接引用 `CausalKnowledge` 的完整接口，而不是一个只读的因果风险端口。
- **单一文件认知复杂度高**：594 行同时处理 SQL、BFS 遍历、反事实分支，难以单人维护。

## 决策

1. 拆分出 **`CausalGraphStore`**（`whyfxpg/core/stores.py`）：
   - 只负责 `causal_nodes` / `causal_edges` / `causal_paths` 的 CRUD。
   - 接受 `UnitOfWork`，与 `AlertStore` / `RiskEventStore` 等保持同一 seam 风格。
   - 提供 `get_node`、`find_nodes`、`add_edge`、`get_causal_chain`、`get_statistics` 等方法。

2. 拆分出 **`CausalReasoning`**（`whyfxpg/services/causal_reasoning.py`）：
   - 纯算法模块，无数据库/网络依赖。
   - 依赖一个 `GraphView` 协议（`get_node` + `get_causal_chain`）。
   - 提供 `factor(event, view)`、`explain(event, view)`、`counterfactual(event, intervention, view)`、`compute_downstream_risk(node_id, view)`。

3. 引入 **`CausalPort`** 抽象（`whyfxpg/ports/causal_port.py`）：
   - 面向 `RiskModel` 的最小接口：
     - `factor(event: dict) -> float`
     - `explain(event: dict) -> str`
     - `counterfactual(event: dict, intervention: dict) -> dict`
   - `RiskModel` 只依赖 `CausalPort`，不再依赖 `CausalKnowledge` 的具体实现。

4. 提供两种适配器：
   - `DbCausalAdapter`（`whyfxpg/adapters/causal/db_causal_adapter.py`）：组合 `CausalGraphStore` + `CausalReasoning`，作为生产默认实现。
   - `InMemoryCausalAdapter`（`whyfxpg/adapters/causal/in_memory_causal_adapter.py`）：内存图 + 同一套推理算法，用于测试与 fixture。

5. 保留 `CausalKnowledge` 作为 **facade**：
   - 旧接口（`add_node`、`add_edge`、`get_causal_factor`、`explain_event`、`counterfactual_risk` 等）保持不变。
   - 内部委托给 `CausalGraphStore` + `CausalReasoning` + `DbCausalAdapter`。
   - 新增 `factor` / `explain` / `counterfactual` 方法作为 `CausalPort` 兼容入口。

6. `RiskModel` 使用 `CausalPort`：
   - `RiskModel.__init__` 增加可选 `causal_port: Optional[CausalPort]` 参数。
   - 默认通过 `DbCausalAdapter(UnitOfWork)` 使用 DB 实现。
   - 测试可注入 `InMemoryCausalAdapter`，无需真实数据库即可验证因果评分路径。

## 影响

- `CausalReasoning` 现在可以在纯内存数据上测试；因果算法与存储 seam 分离。
- `RiskModel` 对因果知识的依赖从宽接口收敛到 `CausalPort` 三个方法，深度模块边界更清晰。
- 新增图数据库（如 Neo4j）或外部因果服务时，只需实现 `CausalPort` / `GraphView`，无需改动 `RiskModel` 或 `CausalReasoning`。
- `CausalKnowledge` 继续作为 WebUI 和旧入口的 facade，调用方无需立即迁移。

## 相关文件

- `whyfxpg/core/stores.py`（新增 `CausalGraphStore`）
- `whyfxpg/services/causal_reasoning.py`（新增 `CausalReasoning` + `GraphView` 协议）
- `whyfxpg/ports/causal_port.py`（新增 `CausalPort`）
- `whyfxpg/adapters/causal/db_causal_adapter.py`（生产适配器）
- `whyfxpg/adapters/causal/in_memory_causal_adapter.py`（内存测试适配器）
- `whyfxpg/adapters/causal/__init__.py`
- `whyfxpg/core/causal_knowledge.py`（重构为 facade）
- `whyfxpg/core/risk_model.py`（改为依赖 `CausalPort`）
- `whyfxpg/tests/test_causal_seams.py`（新增 T6 测试）
- `docs/wayfinder-phase2-5-map.md`
- `docs/architecture-refactor-plan.md`
