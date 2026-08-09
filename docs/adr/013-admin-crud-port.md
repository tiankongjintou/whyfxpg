# ADR-013: Admin CRUD seam — `ConfigStorePort` + `ConfigurationAdminService`

## Status

Accepted / implemented (T15).

## Context

WHYfxpg v2 需要可维护的 CRUD 入口来管理领域对象：数据源、预警规则、风险模型、风险维度、产品分类法。此前所有配置都是手工编辑 YAML 文件，没有版本化、审计或回滚能力。页面层直接依赖文件结构，业务代码中到处是 `cfg.get(...)` 链式访问。

## Decision

- 引入一个 `ConfigStorePort` 作为配置持久化的 seam：业务代码只依赖 `list/read/write/delete/versions` 五个方法，不依赖 YAML 路径或文件格式。
- 提供两个适配器：
  - `FileConfigStoreAdapter`：基于 `Config/*.yaml` 文件集合（source→sources.yaml、rule→alert_rules.yaml、model→risk_model.yaml、dimension→dimensions.yaml、taxonomy→taxonomies.yaml），并把每次发布快照保存到 `Config/objects/<type>/<id>/versions/<version_id>.yaml`。
  - `InMemoryConfigStoreAdapter`：用于测试和沙盒，无需文件系统。
- 提供 `ConfigurationAdminService` 作为应用服务：封装 `create/update/delete/publish/rollback`，并把版本元数据写入 SQLite `config_objects` 表。
- 在 `whyfxpg/config/models.py` 中为 `SourceConfig`、`AlertRule`、`RiskModelConfig`、`SourcesConfig`、`AlertRulesConfig`、`ExtractRulesConfig`、`KeywordsConfig` 增加 `domain_id` 和 `version_id` 字段，同时新增 `RiskDimension` 和 `TaxonomyNode` 类型化配置。
- 新增 Web UI 管理页面：`webui/screens/admin/*.py` 暴露 `render()`，统一调用 `ConfigurationAdminService`；页面层不直接 `open()` 文件或访问数据库。
- 新增 migration `004_config_objects.sql` 创建 `config_objects` 版本表。

## Consequences

- 正向：配置对象可增删改查、版本化、审计、回滚；测试可完全脱离文件系统；为 T16 规则引擎和 T19 多域配置提供统一的配置入口。
- 正向：配置表加入 `domain_id` 后，后续多行业切换只需按 domain 过滤，不需要改存储结构。
- 风险：Admin UI 直接写入生产 YAML 文件，使用不当可能误改风险模型/规则；后续 T16 将为规则提供沙盒和回归测试来缓解。
- 风险：`model` 类型单对象写入整个 `risk_model.yaml`；回滚前需确保理解其影响。

## References

- `whyfxpg/ports/config_store.py`
- `whyfxpg/adapters/config/file_config_store.py`
- `whyfxpg/adapters/config/in_memory_config_store.py`
- `whyfxpg/services/admin/configuration_admin_service.py`
- `whyfxpg/services/admin/config_object_store.py`
- `whyfxpg/webui/screens/admin/common.py`
- `whyfxpg/migrations/004_config_objects.sql`
- `whyfxpg/tests/test_configuration_admin_service.py`
- `whyfxpg/tests/test_file_config_store_adapter.py`
- `whyfxpg/tests/test_admin_ui_screens.py`
- `whyfxpg/tests/test_db.py`
