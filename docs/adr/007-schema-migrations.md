# ADR-007: 使用轻量 MigrationRunner 替代 `init_db` 管理 schema

## 状态

已实施（2026-07-29）。

## 背景

原有 `whyfxpg.core.db.init_db()` 把全部 `CREATE TABLE` / `CREATE INDEX` 与 `ALTER TABLE ADD COLUMN` 写在一个 222 行的函数里，存在几个问题：

1. **Schema 与迁移逻辑混合**：每次改动列都要编辑 `init_db` 主体，容易破坏新建数据库与既有数据库两条路径。
2. **静默吞错**：列变更用 `try/except OperationalError` 包裹，真实语法错误也会被忽略。
3. **无法重放/回滚**：无法判断哪些 schema 变更已应用到某个数据库，难以在多环境（开发/测试/用户本地）保持一致。
4. **测试开销**：测试若需重建 schema，必须依赖 `init_db` 的全量实现，无法单独应用某个表结构。

## 决策

引入轻量版 `MigrationRunner`：

- 每个 migration 是一个文件，位于 `whyfxpg/migrations/`，命名格式 `NNN_description.sql` 或 `NNN_description.py`。
- 已执行版本记录在 `schema_migrations(version TEXT PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)` 表中。
- 启动时按版本号顺序扫描未执行的 migration，逐个应用并记录版本；失败时抛出异常，已执行版本不记录。
- `.sql` 文件支持多条语句，按分号拆分；`.py` 文件必须暴露 `run(conn: sqlite3.Connection) -> None`。
- 不引入 Alembic、Flyway 等重型工具，保持 WHYfxpg 单进程/单人维护的轻量属性。
- `init_db()` 保留为兼容 shim，内部调用 `MigrationRunner`；新代码建议直接使用 `MigrationRunner(conn).run()`。

## 已有 migration

| 编号 | 文件 | 说明 |
|---|---|---|
| 001 | `001_init_schema.sql` | 初始业务表：`monitor_sources`, `raw_pages`, `risk_events`, `alert_records`, `manual_reviews`, `crawl_logs`, `config_versions`, 汇总表，索引 |
| 002 | `002_causal_graph.sql` | 因果知识图谱表：`causal_nodes`, `causal_edges`, `causal_paths` 与索引 |
| 003 | `003_add_causal_factor.py` | 向后兼容：为已有 `risk_events` 表添加 `causal_factor` 列（仅当不存在时） |

## 影响

- `whyfxpg/core/db.py`：`init_db` 改为调用 `MigrationRunner`，仍负责 `journal_mode=WAL` 与 `busy_timeout=10000`。
- `whyfxpg/core/stores.py`：`CausalGraphStore.ensure_schema()` 不再持有独立 DDL 字符串，而是通过 `MigrationRunner` 统一应用，避免重复。
- `whyfxpg/migrations/runner.py`：核心 `MigrationRunner` 实现。
- `scripts/enable_wal.py`：改为直接使用 `MigrationRunner` 初始化 schema，再设置 WAL。
- 测试：新增 `whyfxpg/tests/test_migration_runner.py` 7 条；`conftest`、测试 fixture 全部改为 `MigrationRunner`。

## 回滚与兼容

- 对已有 `whyfxpg.db`：第一次启动时 `MigrationRunner` 会创建 `schema_migrations` 表，并把所有 migration 标记为已应用（`CREATE TABLE IF NOT EXISTS` 不会破坏数据，003 会检查列是否已存在）。
- 新环境：直接按顺序执行所有 migration 即可。
- 如果某条 migration 失败，只有该版本不会被记录；其余已执行版本保持成功状态，修复后可重新运行。

## 后续约定

- 新增表/字段/索引必须新增 `NNN_*.sql` 或 `NNN_*.py`，版本号递增，不得再修改 `init_db` 主体。
- 对于已有表的列变更，优先用 `.py` migration 检查列是否存在，避免重复添加。
- 测试需要特定 schema 时，通过 `MigrationRunner(conn).run(target="NNN")` 精确控制。

## 替代方案（已排除）

- **Alembic / SQLAlchemy**：增加依赖和配置复杂度，对单人维护项目过重。
- **保留 `init_db` 但拆成函数**：只解决了局部可读性，没有解决“已应用哪些变更”和“多环境一致”的问题。
- **手动 schema_version 硬编码在 `init_db` 内**：与当前方案类似，但把所有逻辑仍集中在 `db.py`，不符合“改一个概念只改一个文件”的 locality 原则。
