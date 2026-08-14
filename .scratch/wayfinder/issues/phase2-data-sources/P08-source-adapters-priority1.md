# P08 — 数据源扩充：第一优先级 × 4

**What to build:**
实现加拿大卫生部、新加坡消费者保护局、日本消费者厅、韩国产品安全院 4 个数据源适配器，复用 `BaseSourceAdapter` 框架，目标是接入时间从"1周/源"降低到"1天/源"。

**Blocked by:** P03-core-rest-api.md (API 端点就绪后可对接)

**Status:** completed

**Resolution (2026-08-14):**
- `whyfxpg/ports/source_adapter.py`：新建 `BaseSourceAdapter` ABC + `SourceResponse` dataclass + `SourceRegistry` 注册表
- `whyfxpg/adapters/sources/canada_health_adapter.py`：CanadaHealthAdapter，英法双语 ✅
- `whyfxpg/adapters/sources/japan_caa_adapter.py`：JapanCAAAdapter，日文编码处理 ✅
- `whyfxpg/adapters/sources/singapore_cpss_adapter.py`：SingaporeCPSSAdapter ✅
- `whyfxpg/adapters/sources/korea_safety_adapter.py`：KoreaSafetyAdapter，韩英双语 ✅
- `whyfxpg/adapters/sources/registry.py`：SourceRegistry 实现
- `whyfxpg/adapters/sources/__init__.py`：注册 4 个新适配器
- `Config/sources.yaml`：补 4 个新数据源条目
- Commits: `cd31921` (3 adapters), `77fba32` (Korea adapter)

## Acceptance criteria

- [ ] `RapexAdapter` → 欧盟 Safety Gate（参考实现，需验证框架可用性）
- [ ] `CanadaHealthAdapter` — 加拿大卫生部适配器，英文/法文双语
- [ ] `SingaporeCPSSAdapter` — 新加坡消费者保护局适配器
- [ ] `JapanCAAAdapter` — 日本消费者厅适配器（需要处理日文编码）
- [ ] `KoreaSafetyKoreaAdapter` — 韩国产品安全院适配器
- [ ] 每个适配器实现 `fetch(since)` + `parse(raw)` + `health_check()`
- [ ] 每个适配器注册到 `SourceRegistry`
- [ ] 健康检查：连续 3 次失败自动降级并记录 `sources.status='error'`
- [ ] 4 个数据源合计新增风险事件入库

## References

- `docs/技术改造路线图.md` §5.1 数据源扩充清单（第一优先级）
- `docs/技术改造路线图.md` §3.3 BaseSourceAdapter 接口定义
