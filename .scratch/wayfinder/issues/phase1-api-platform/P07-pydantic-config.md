# P07 — Pydantic 配置 Schema 校验

**What to build:**
用 Pydantic 模型替换 YAML 配置，实现类型校验和降级策略。Phase 1 期间所有业务配置（risk_model、dimensions、rules）迁移到 Pydantic，并支持从环境变量注入。

**Blocked by:** None — can start immediately (parallel with P01–P04)

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1** `whyfxpg/config/pydantic_models.py`：Pydantic v2 BaseModel 定义
  `RiskModelConfig`（含 LevelConfig/RiskMatrixConfig/HistoryFactorConfig）、
  `DimensionConfig`、`AlertRuleConfig`，全部带默认值 + `from_dict` 兼容接口。
- **AC-2** `whyfxpg/config/pydantic_loader.py`：`load_risk_model()` YAML →
  环境变量覆盖 → Pydantic 校验；结构性错误（缺 version / severity_levels 空）
  抛 `ConfigValidationError` 拒绝启动，错误信息含字段路径。
- **AC-3** 环境变量覆盖：`RISK_MODEL__<PATH>`（嵌套 `__` 分隔，值 JSON 解析，
  大小写智能匹配——如 `RISK_MODEL__RISK_LEVEL_THRESHOLDS__S=90`）。
- **AC-4** 降级策略：单字段校验失败或缺省时回退默认值，不影响整体启动。
- **AC-5** `risk_scorer.py` 重构：`__init__` 类型标注与 `assess()` 均改用
  Pydantic 模型；`ConfigLoader.typed_risk_model` 切换到 `load_risk_model()`，
  `RiskModel`/`RiskEvaluationRunner`/`extract_engine` 自动受益。
- **AC-6** 现有 pytest 通过：全量 276 passed（新增 12 个 P07 测试）；
  兼容适配 1 处测试配置（test_pipeline_archive_seam 的 risk_model.yaml
  补 severity_levels）。
- **文档**：`docs/06-开发环境与运行指南.md` 新增 §4.4 配置加载与环境变量。

## Acceptance criteria

- [ ] `whyfxpg/config/pydantic_models.py` — Pydantic BaseModel 定义 RiskModelConfig、DimensionConfig、AlertRuleConfig
- [ ] YAML 配置文件通过 Pydantic 校验后才加载，校验失败拒绝启动并输出明确错误
- [ ] 支持环境变量覆盖配置字段（如 `RISK_MODEL__SEVERITY_WEIGHTS`）
- [ ] 降级策略：某字段校验失败时使用默认值，不影响整体启动
- [ ] 重构 `whyfxpg/core/risk_scorer.py` 使用 Pydantic 模型，而非直接读取 YAML
- [ ] 现有 pytest 全部通过（配置加载路径变化需兼容）

## References

- `docs/技术改造路线图.md` §6.2 Phase 0 期间清理
