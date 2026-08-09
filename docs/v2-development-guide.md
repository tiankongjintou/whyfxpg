# WHYfxpg v2 开发指南

这份指南面向继续扩展 WHYfxpg v2 的开发者。核心设计原则是 **Port/Adapter 先行的 seam-first 架构**：业务逻辑只依赖接口契约，技术实现通过适配器注入。

## 1. 包结构约定

| 目录 | 职责 | 示例 |
|---|---|---|
| `whyfxpg/ports/` | 领域接口（Port）与数据模型 | `source_port.py`, `llm_port.py` |
| `whyfxpg/adapters/` | 生产实现 + InMemory 测试替身 | `sources/http_source_adapter.py`, `sources/in_memory_source_adapter.py` |
| `whyfxpg/core/` | 数据访问、管道、引擎、规则、评分 | `stores/`, `information_pipeline.py`, `risk_scorer.py` |
| `whyfxpg/services/` | 业务编排与 UI 门面 | `pipeline_orchestrator.py`, `dashboard_builder.py` |
| `whyfxpg/webui/` | Streamlit 页面，只调用 `services/` | `screens/*.py` |

禁止跨层直接调用：

- `webui/` 不直接 import `core.db` 或 `adapters/` 的具体实现。
- `adapters/` 不直接 import `webui/` 或 `services/` 的业务逻辑。
- `core/` 不直接依赖 `.env` 中的 API 密钥；配置统一通过 `ConfigLoader` 读取，LLM 调用统一走 `LLMPort`。

## 2. 新增一个 Port 的标准流程

以新增一个“通知发布”渠道为例：

1. **定义 Port** 在 `whyfxpg/ports/alert_publisher.py`：
   - 抽象基类（ABC）声明业务方法。
   - 数据类（dataclass）声明输入/输出模型。

2. **提供生产适配器** 在 `whyfxpg/adapters/alerts/sms_publisher_adapter.py`。

3. **必须提供 InMemory 测试替身** 在 `whyfxpg/adapters/alerts/in_memory_alert_publisher.py`。`tests/` 中 90% 的测试应使用这个替身。

4. **在应用服务中使用 Port** 而非具体实现。构造函数注入，默认使用生产适配器，测试时传入 InMemory 替身。

5. **新增测试**：
   - Port 本身测试（至少验证两个适配器实现同一接口）。
   - 业务使用路径测试（用 InMemory 替身验证行为）。

## 3. 新增一个流水线阶段

1. 在 `whyfxpg/core/information_pipeline.py` 的 `PipelineStage` 中声明阶段，按 `order` 排序。
2. 在 `whyfxpg/services/pipeline_orchestrator.py` 或上层配置里注册 `stage_runner`：

```python
def _my_stage(ctx: PipelineContext) -> StageResult:
    ...
    return StageResult(status="success", output={...}, archive=True, artifact_type="my_artifacts")
```

3. 如果阶段产物需要归档，设置 `archive=True`，`archive_port` 会自动持久化。
4. 在 `whyfxpg/tests/test_pipeline_archive_seam.py` 或新增测试文件中覆盖该阶段。

## 4. 新增一个大屏 Widget

1. 在 `whyfxpg/webui/dashboard_models.py` 确认 WidgetSpec 类型已支持所需的 `query` 格式。
2. 在 `whyfxpg/services/dashboard_builder.py` 的 `WidgetRegistry` 中注册新的 `widget_type` 和 `load_fn`。
3. 在 `whyfxpg/adapters/dashboard/dashboard_read_model_adapter.py` 中实现对应的 `query` 解析。
4. 在 `config/dashboard_templates/` 或测试中创建模板，运行 `DashboardBuilderService` 验证。
5. 如需导出，在 `whyfxpg/adapters/dashboard/` 新增 `DashboardExportPort` 实现。

## 5. 测试策略

| 层级 | 测试目标 | 运行方式 |
|---|---|---|
| Port 适配器 | 两种实现行为一致 | `pytest whyfxpg/tests/test_*_seam.py` |
| 业务服务 | 用 InMemory 适配器验证编排 | 新增 `test_*_service.py` |
| 端到端 | 完整流水线行为 | `pytest whyfxpg/tests/test_v2_integration.py` |
| 架构守护 | 防止 seam 泄漏 | `python scripts/check_architecture.py` |

### 本地运行

```bash
# 全部测试（不计算覆盖率）
python scripts/run_tests.py

# 单文件调试
.venv/Scripts/python -m pytest whyfxpg/tests/test_v2_integration.py -v

# 架构检查
.venv/Scripts/python scripts/check_architecture.py
```

### 测试原则

- 不依赖真实网络、真实 LLM、真实数据库。
- `conftest.py` 已通过 autouse fixture 拦截所有 `OpenAICompatAdapter.chat_completion` 调用，避免误触发付费 API。
- 需要真正网络/LLM 的测试显式在 fixture 中恢复或单独标注，并只在手动环境运行。

## 6. 配置管理

- 所有配置在 `config/` 目录下，以 YAML 为主存储。
- 运行时配置通过 `ConfigLoader` 读取；配置对象通过 `ConfigurationAdminService` 写入（审计版本）。
- 新增配置类型时：
  1. 在 `whyfxpg/core/typed_config.py` 定义数据类。
  2. 在 `ConfigLoader` 中增加 `typed_*` 方法。
  3. 在 `Config/domains/<domain>/` 下提供默认值，并新增测试验证解析。

## 7. 数据库迁移

- 使用自研 `MigrationRunner`（`whyfxpg/core/migration_runner.py`），按版本顺序执行 `scripts/migrations/` 下的 `.sql` 和 `.py` 脚本。
- 不要在业务代码中直接调用 `init_db()` 或 `PRAGMA` 修改模式；所有 schema 初始化/升级走 `MigrationRunner`。
- 新增 migration 时：
  1. 命名：`NNN_description.sql` 或 `.py`。
  2. 在 `whyfxpg/tests/test_migration_runner.py` 中验证升级与回退（如适用）。
  3. 更新 `docs/adr/007-schema-migrations.md` 或新增 ADR。

## 8. 添加新的风险评估维度

1. 在 `whyfxpg/core/typed_config.py` 的 `RiskModel` 或相关维度配置中增加字段。
2. 在 `whyfxpg/core/risk_scorer.py` 中新增评分因子函数。
3. 在 `whyfxpg/core/risk_evaluation_runner.py` 中把因子乘入总分。
4. 在 `Config/risk_model.yaml` 或默认领域配置中提供默认值。
5. 新增 `whyfxpg/tests/test_risk_scorer.py` 测试用例，确保维度独立且可解释。

## 9. 常见陷阱

- **跨层导入**：`webui/screens/*.py` 不能直接 import `core.db`。先问自己：“这个行为是否属于某个业务服务？如果是，把它下沉到 `services/`。”
- **全局状态**：不要使用单例。所有外部依赖通过构造函数注入。
- **直接写 `.env` 读取代码**：`.env` 解析统一在 `whyfxpg/adapters/llm/_provider_config.py` 和 `ConfigLoader` 中；业务代码不要直接 `os.environ` 读取密钥。
- **测试写生产库**：`tests/` 使用 `initialized_db` fixture，它创建临时 SQLite；不要用 `whyfxpg/data/whyfxpg.db` 跑测试。
- **新模块未提供 InMemory 适配器**：这会导致测试依赖真实网络或 API，违反 v2 原则。

## 10. 提交前检查清单

- [ ] 新增/修改代码通过了 `python scripts/run_tests.py`
- [ ] 通过了 `python scripts/check_architecture.py`
- [ ] 新增 Port 同时提供了生产适配器 + InMemory 适配器
- [ ] 新增业务逻辑有测试覆盖，且测试使用 InMemory 适配器
- [ ] `.env` 中的真实密钥未被提交（使用 `[REDACTED]` 或 `.env.example`）
- [ ] 如果涉及 schema 变更，已新增 migration 并验证
- [ ] 如果涉及架构决策，已新增/更新 `docs/adr/*.md`

## 参考

- `docs/adr/` 记录了每个重要架构决策。
- `whyfxpg/tests/test_v2_integration.py` 展示了如何把所有 seams 串成一条端到端流水线。
- `whyfxpg/tests/test_dashboard_v2_seam.py`、`test_rule_engine_seam.py`、`test_pipeline_archive_seam.py` 是典型 seam 测试示例。
