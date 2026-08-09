# ADR-010: 类型化配置模型（Phase 4D）

## 状态

已接受（2026-07-31）

## 上下文

随着 T2~T10 的 seam 拆分完成，业务模块（RiskScorer、AlertEngine、Fetcher、ExtractEngine）
仍然通过 `ConfigLoader` 以裸 `dict` 访问配置。问题包括：

- 字段访问无类型提示，重构时依赖全局搜索。
- `KeyError` 或 `dict.get` 默认值散落在各业务模块。
- 配置结构变更时缺少单点收口。

Phase 4D 的目标是在不引入重型依赖（如 Pydantic）的前提下，
用标准库 `dataclasses` 将核心 YAML 配置转换为类型化对象。

## 决策

1. **使用 `dataclasses` 而非 Pydantic**
   - 项目当前无 Pydantic 依赖；为单一配置层引入新包收益不足。
   - `dataclasses` + 手工 `from_dict` 足以表达嵌套结构，并保留运行时默认值回退。

2. **新增 `whyfxpg/config/models.py`**
   - 为 `risk_model.yaml`、`sources.yaml`、`alert_rules.yaml`、`extract_rules.yaml`、`keywords.yaml`
     分别建立顶层 model：`RiskModelConfig`、`SourcesConfig`、`AlertRulesConfig`、`ExtractRulesConfig`、`KeywordsConfig`。
   - 关键嵌套子结构也建模：`LevelConfig`、`RiskMatrixConfig`、`HistoryFactorConfig`、`SourceConfig`、`AlertRule`、`ExtractRule`、`KeywordSet`。

3. **在 `ConfigLoader` 中保留裸 dict 属性，新增 `typed_*` 属性**
   - `loader.risk_model` 仍返回 dict，确保旧调用方不破坏。
   - `loader.typed_risk_model`、`typed_sources`、`typed_alert_rules`、`typed_extract_rules`、`typed_keywords`
     返回类型化对象，新代码逐步迁移。

4. **业务模块逐步迁移**
   - `RiskScorer`、`RiskEvaluationRunner`、`RiskModel` 使用 `RiskModelConfig`。
   - `AlertEngine` 使用 `AlertRulesConfig` / `AlertRule`。
   - `Fetcher` 使用 `SourcesConfig` / `SourceConfig`，并在与旧 dict 接口的 `SourcePort`/`MonitorSourceStore` 交互时通过 `to_dict()` 桥接。
   - `ExtractEngine` 使用 `ExtractRulesConfig` / `ExtractRule` 和 `RiskModelConfig`。

5. **配置字段与 Python 关键字冲突处理**
   - `extract_rules.yaml` 中的 `field` 键与 Python 关键字 `field` 冲突，
     将 dataclass 属性命名为 `field_name`，`from_dict` 中从 `field` 键读取。

6. **默认分支通过单元测试保证**
   - 新增 `whyfxpg/tests/test_config_models.py` 覆盖各 model 的解析、默认值、启用过滤、to_dict 递归转换。

## 后果

### 正面

- 业务模块不再依赖 `dict.get` 链式调用，字段访问有类型提示和 IDE 补全。
- 配置结构变更集中在 `whyfxpg/config/models.py`，降低回归风险。
- 无新增外部依赖，部署包体积与复杂度不变。
- 全量测试通过（123 passed）。

### 负面

- 新增 `from_dict` 样板代码；后续若配置结构大量增加，维护成本上升。
- `to_dict()` 桥接点仍保留 dict 接口，未来如 SourcePort/Store 全面类型化后可移除。

## 相关文件

- `whyfxpg/config/models.py`
- `whyfxpg/config/__init__.py`
- `whyfxpg/core/config_loader.py`
- `whyfxpg/core/risk_scorer.py`
- `whyfxpg/core/risk_evaluation_runner.py`
- `whyfxpg/core/risk_model.py`
- `whyfxpg/core/alert_engine.py`
- `whyfxpg/core/fetcher.py`
- `whyfxpg/core/extract_engine.py`
- `whyfxpg/tests/test_config_models.py`
