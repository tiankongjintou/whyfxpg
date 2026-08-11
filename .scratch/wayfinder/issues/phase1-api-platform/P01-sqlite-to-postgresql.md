# P01 — SQLite → PostgreSQL 多租户迁移

**What to build:**
建立 Phase 1 的数据库骨架：从 SQLite 迁移到 PostgreSQL，并实现多租户数据模型（accounts 表 + risk_events/alerts 加 account_id 外键）。引入 Alembic 作为 schema 迁移框架。

**Blocked by:** None — can start immediately

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **Alembic 骨架**：`alembic/` + `alembic.ini`（`sqlalchemy.url` 默认指向
  `postgresql://user:pass@localhost:5432/whyfxpg`），`env.py` 支持
  `DATABASE_URL` 环境变量覆盖（本地验证可设 `sqlite:///...`）。
- **0001 迁移**（`alembic/versions/0001_accounts_multitenancy.py`，自包含）：
  `accounts` 表（8 列，UUID PK）、`risk_events`/`alert_records` 加
  `account_id` 外键、`risk_events` 补 `created_at`（对齐路线图 §4.2）、
  3 个索引 `idx_risk_events_account/manufacturer/created`；up/downgrade
  均验证（downgrade 用 batch_alter_table 仅回退增量）。
- **双 DB 切换（AC-7）**：`whyfxpg/core/db.py` 新增 `get_database_url()` /
  `is_postgres_url()`，`DATABASE_URL` 环境变量切换；默认回退 SQLite，
  Phase 0 主链路零改动（全量 264 passed 验证）。
- **数据迁移脚本**（AC-6）：`scripts/migrate_sqlite_to_postgres.py` +
  纯函数 `whyfxpg/migrations/sqlite_to_pg.py`（类型映射/DDL 生成），
  流程：alembic upgrade → 自动 DDL 建其余表 → 逐表拷贝 → 行数校验。
- **测试**：`whyfxpg/tests/test_p01_multitenancy.py` 21 个用例
  （迁移结构/回滚/URL 切换/类型映射/DDL 生成），全部通过。
- **文档**：`docs/03-数据库设计说明书.md` 概览/表结构/ER 关系同步。

### ⚠️ PG 实机验证待环境（用户已确认）

本机无 PostgreSQL 服务，以下 AC 仅完成代码/脚本部分，实机验证待
DATABASE_URL 指向可用 PG 后执行：

- AC-1 的 PG 实连部分（alembic.ini 已指向 PG，未实连验证）
- AC-6 的 SQLite→PG 数据迁移实机验证（脚本已就绪，未在 PG 上运行）
- 验证命令：`python scripts/migrate_sqlite_to_postgres.py --sqlite data/whyfxpg.db`

## Acceptance criteria

- [ ] Alembic 初始化完成，`alembic.ini` 指向 PostgreSQL 数据库
- [ ] `accounts` 表创建：id(UUID), company_name, plan_type, api_key_hash, api_key_prefix, monthly_quota, created_at, status
- [ ] `risk_events` 表加 `account_id` 外键（UUID REFERENCES accounts），实现租户隔离
- [ ] `alert_records` 表加 `account_id` 外键
- [ ] 建立 `idx_risk_events_account`、`idx_risk_events_manufacturer`、`idx_risk_events_created` 索引
- [ ] SQLite 数据可完整迁移到 PostgreSQL（迁移脚本验证）
- [ ] Phase 0 的 whyfxpg 包仍可独立运行（不依赖 PostgreSQL），通过环境变量切换 DB
- [ ] 文档更新：`docs/03-数据库设计说明书.md` 同步新的 schema

## References

- `docs/技术改造路线图.md` §4.2 数据库改造
- `docs/03-数据库设计说明书.md`
