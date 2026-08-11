# P1b-02 — stores 清理:pipeline_store 兼容层去重

**What to build:**
§6.2-2「stores/ 目录结构混乱,统一为 Repository 模式,删除重复实现」的务实落地。
BaseStore + UnitOfWork 统一模式已存在(TD03 前);剩余重复是
`core/pipeline_store.py`——archive_store 的 5 行 re-export 兼容层,仍被 3 处
旧路径引用。将其迁移到规范路径后删除,消除重复。

**Blocked by:** None

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- AC-1 ✅ 3 处旧路径迁移:feedback_learning_service / pipeline_orchestrator /
  test_pipeline_archive_seam → `whyfxpg.core.stores.archive_store`。
- AC-2 ✅ 删除 `whyfxpg/core/pipeline_store.py`(5 行 re-export 兼容层完成使命)。
- AC-3 ✅ 全项目 grep 无 pipeline_store 残留。
- AC-4 ✅ 全量 341 passed + ruff/mypy 全绿(ruff 顺带修复 2 处 import 排序)。
- AC-5 ✅ 无 schema/API 变更,无需 docs/03/04 更新。
- 说明:DomainConfigStore/RuleStore 为只读配置读取器(不碰 DB),保留
  独立于 UnitOfWork 的设计是正确决策,不强行统一。

## Acceptance criteria

- [ ] 3 处旧路径调用迁移到 `whyfxpg.core.stores.archive_store`:
      feedback_learning_service / pipeline_orchestrator / test_pipeline_archive_seam
- [ ] 删除 `whyfxpg/core/pipeline_store.py`
- [ ] 全项目 grep 确认无 `pipeline_store` 残留引用
- [ ] 全量 pytest 通过 + ruff/mypy 无 ERROR
- [ ] 文档:不涉及 schema/API,无需 docs/03/04 更新(如有必要补说明)

## References

- 路线图 §6.2「stores/ 目录结构混乱 — 统一为 Repository 模式,删除重复实现」
- `whyfxpg/core/stores/archive_store.py`(规范实现)
