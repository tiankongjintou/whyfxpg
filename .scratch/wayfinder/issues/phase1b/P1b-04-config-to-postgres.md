# P1b-04 — 配置迁移 PG:配置存储 DB 后端(§6.3-2)

**What to build:**
§6.3-2「配置与代码耦合 — 所有业务配置迁移到 PostgreSQL,去 YAML 化」的
存储层落地。新增 `DbConfigStoreAdapter`(config_objects 表后端,与
FileConfigStoreAdapter 互为替代)、PG 侧 Alembic 0004 迁移、YAML→DB
导入工具。运行时加载仍走 YAML(路线图 72 行:YAML 保留为包内默认),
DB 后端作为配置管理入口的目标存储与审计源。

**Blocked by:** None

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- AC-1 ✅ DbConfigStoreAdapter(config_objects 表后端),5 方法全实现;
  list 用 ROW_NUMBER() 窗口取每 object 最新版(SQLite 3.25+/PG 通用)。
- AC-2 ✅ 当前配置 = 最新 version;delete→deprecated;write 新版本。
- AC-3 ✅ Alembic 0004:config_objects 表 + 2 索引,对齐 SQLite 004。
- AC-4 ✅ import_yaml_configs(基于 FileConfigStoreAdapter 分片约定),
  幂等:内容未变跳过。
- AC-5 ✅ 7 个测试:CRUD/版本排序/导入幂等/迁移建表。
- AC-6 ✅ 全量 349 passed + ruff/mypy 全绿。
- AC-7 ✅ docs/03 新增 2.18 config_objects 节。
- 说明:运行时加载仍读 YAML(包内默认,路线图 72 行);DB 后端是配置管理
  目标存储;真正的"运行时去 YAML 化"(ConfigLoader 读 DB)留待后续 ticket。
- ⚠️ PG 实机验证留待环境。

## Acceptance criteria

- [ ] DbConfigStoreAdapter 实现 ConfigStorePort:list/read/write/delete/versions,
      跨 SQLite/PostgreSQL 通用 SQL
- [ ] 语义:当前配置 = 每个 object_id 最新版本;delete 标记 deprecated(可审计);
      write 产生新版本
- [ ] Alembic 0004:PG 侧 config_objects 表(对齐 SQLite 004)
- [ ] import_yaml_configs:配置目录 → DB 导入,幂等(内容未变跳过)
- [ ] 测试:CRUD/版本/导入 + 迁移验证(SQLite 端;PG 实机验证留待环境)
- [ ] 全量 pytest + ruff + mypy 全绿
- [ ] docs/03 新增 config_objects 表说明
