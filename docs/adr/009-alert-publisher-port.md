# ADR-009：引入 `AlertPublisher` 端口统一预警写入

## 状态

已接受（Accepted），2026-07-31。

## 背景

系统有两处写入 `alert_records` 的代码：

1. `AlertEngine`（`whyfxpg/core/alert_engine.py`）：实现了一套去重/插入逻辑，但紧耦合在规则引擎内部。
2. `RiskPredictor.write_predictive_alerts`（`whyfxpg/core/risk_predictor.py`）：直接执行 `INSERT` SQL 和去重查询，与 `AlertEngine` 的去重逻辑重复。

这导致：

- **预警写入 seam 不统一**：同一概念（alert record）有两条写入路径，去重规则可能不一致。
- `RiskPredictor` 无法脱离数据库测试其预警写入路径。
- 后续若需支持消息队列、邮件、Webhook 等预警通道，需要同时修改两处。

## 决策

1. 引入 **`AlertPublisher`** 端口（`whyfxpg/ports/alert_publisher.py`）：
   - 单一方法 `publish(alert: dict) -> bool`。
   - `alert` 记录必须包含 `rule_id`、`rule_name`、`object_type`、`object_value`、`severity`、`triggered_value`、`description`。

2. 提供两种适配器：
   - `DbAlertPublisher`（`whyfxpg/adapters/alerts/db_alert_publisher.py`）：基于现有 `AlertStore`，复用 `find_existing` 去重与 `insert_alert` 插入。
   - `InMemoryAlertPublisher`（`whyfxpg/adapters/alerts/in_memory_alert_publisher.py`）：记录所有发布请求，用于测试与 fixture。

3. 重构 **`AlertEngine`**：
   - 新增可选 `publisher_factory: Callable[[AlertStore], AlertPublisher]` 参数，默认使用 `DbAlertPublisher`。
   - 规则方法不再直接调用 `AlertStore.insert_alert`，而是通过 `_publish_alert` 组装记录并调用 `publisher.publish`。
   - 保留 `run(uow=None)` 入口与现有行为不变。

4. 重构 **`RiskPredictor.write_predictive_alerts`**：
   - 新增可选 `publisher` 与 `uow` 参数。
   - 默认在内部打开 `UnitOfWork` 并使用 `DbAlertPublisher`。
   - 去重/插入逻辑完全委托给 `AlertPublisher`。

## 决策依据

- **Locality**：预警去重与插入逻辑集中到 `AlertPublisher` 实现中，不再散落在规则引擎与预测器内。
- **Seam / Adapter**：新增一个端口 + 两个适配器，使预警写入成为可替换的 seam，符合 codebase-design 中“两个 adapter 才让 seam 成立”的原则。
- **Test surface**：`AlertEngine` 与 `RiskPredictor` 的预警写入路径现在都可以通过 `InMemoryAlertPublisher` 在内存中测试。
- **兼容性**：`AlertEngine` 与 `RiskPredictor` 的默认构造与入口签名保持不变；新增参数均为可选注入。

## 影响

- 新增文件：
  - `whyfxpg/ports/alert_publisher.py`
  - `whyfxpg/adapters/alerts/__init__.py`
  - `whyfxpg/adapters/alerts/db_alert_publisher.py`
  - `whyfxpg/adapters/alerts/in_memory_alert_publisher.py`
- 修改文件：
  - `whyfxpg/core/alert_engine.py`
  - `whyfxpg/core/risk_predictor.py`
- 新增测试：
  - `whyfxpg/tests/test_alert_publisher.py`（3 条）
  - `whyfxpg/tests/test_alert_engine.py`（+1 条 seams 测试）
  - `whyfxpg/tests/test_risk_predictor.py`（3 条）
- 全量 pytest 从 108 条增加到 **115 条**。
- 后续新增预警通道（邮件/短信/企业微信）时，只需实现 `AlertPublisher` 并注入，无需改动 `AlertEngine` 或 `RiskPredictor`。

## 相关文件

- `whyfxpg/ports/alert_publisher.py`
- `whyfxpg/adapters/alerts/db_alert_publisher.py`
- `whyfxpg/adapters/alerts/in_memory_alert_publisher.py`
- `whyfxpg/adapters/alerts/__init__.py`
- `whyfxpg/core/alert_engine.py`
- `whyfxpg/core/risk_predictor.py`
- `whyfxpg/tests/test_alert_publisher.py`
- `whyfxpg/tests/test_alert_engine.py`
- `whyfxpg/tests/test_risk_predictor.py`
