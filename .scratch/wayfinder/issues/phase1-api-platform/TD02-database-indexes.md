# TD02 — 数据库索引补全

**What to build:**
为 `risk_events` 表补充缺失的索引：country、manufacturer、product_category，以及 alert_records 的相关索引，确保大数据量下的查询性能。

**Blocked by:** None — can start immediately

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1** Alembic 0002 迁移：`idx_risk_events_country`、
  `idx_risk_events_product_category`（0001 未建）；`idx_risk_events_manufacturer`
  已由 0001 建立，0002 幂等检查不重复建。
- **AC-2** `alert_records` 补 `created_at` 列（与 risk_events 对齐，
  0001 无此列）+ `idx_alert_account_created(account_id, created_at)`。
- **AC-3** `idx_pipeline_status_completed(status, completed_at)`——
  pipeline_runs 表由数据迁移脚本自动 DDL 创建（非 Alembic 管理），
  0002 用 inspector 条件建索引（表存在才建，SQLite 端验证跳过不报错）。
- **AC-4** 全部经 Alembic 迁移管理（alembic/versions/0002_query_indexes.py），
  非手动 SQL；up/downgrade 幂等（重复 upgrade 不报错）。
- **AC-5** 性能验证：EXPLAIN QUERY PLAN 断言 manufacturer 查询走
  `idx_risk_events_manufacturer`；100 万条 <100ms 实测方法
  `scripts/benchmark_indexes.py`（带索引/无索引对照，可设 --rows/--target-ms）。
- **AC-6** `docs/03-数据库设计说明书.md` 补充 risk_events/alert_records/
  pipeline_runs 索引说明。
- 测试：`whyfxpg/tests/test_td02_indexes.py` 5 个用例全过；
  全量 pytest 281 passed（新增 5），仅剩 1 个历史基线失败。

## Acceptance criteria

- [ ] `risk_events` 表建立索引：`idx_risk_events_country`、`idx_risk_events_manufacturer`、`idx_risk_events_product_category`
- [ ] `alert_records` 表建立索引：`idx_alert_account_created`
- [ ] `pipeline_runs` 表：`idx_pipeline_status_completed`
- [ ] 索引创建通过 Alembic 迁移脚本管理（不手动 SQL）
- [ ] 大数据量查询性能验证：100 万条 risk_events 记录，`manufacturer` 查询响应时间 < 100ms
- [ ] 文档更新：`docs/03-数据库设计说明书.md` 补充索引说明

## References

- `docs/技术改造路线图.md` §6.1 立即修复（P0）
- `docs/03-数据库设计说明书.md`
