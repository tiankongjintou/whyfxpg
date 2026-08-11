# P03 — 核心 REST API 端点

**What to build:**
实现 `docs/技术改造路线图.md` §4.4 规定的所有核心 REST API 端点，统一响应格式，带分页/筛选支持。

**Blocked by:** P02-fastapi-skeleton-auth.md

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1~7 端点**：`whyfxpg_api/routes/` 新增 events.py（列表分页+筛选/
  详情/assess 带 breakdown/batch-assess ≤100）、alerts.py（列表+详情）、
  companies.py（企业画像）。
- **AC-8 统一响应**：`schemas/api_response.py` 定义
  `{"success": true, "data", "meta": {request_id, quota_used, quota_remaining}, "error": null}`，
  路由经 `ok_response()` 包装（meta 从 request.state 读取，为 P04 预留）。
- **AC-9 租户隔离**：`EventQueryPort` 全部查询方法强制带 account_id；
  测试验证账户 B 查不到账户 A 的事件/预警。
- **数据层**：`ports/event_query_port.py`（Port）+ `adapters/events/`
  Pg/InMemory 双适配器（seam-first 约定）；create_app 按 DATABASE_URL
  智能选择（无 PG 时 InMemory 本地模式）。
- 测试：`test_api_events.py` 15 个用例（分页/筛选/详情/评分/batch/画像/
  预警/隔离），全量 pytest 306 passed（仅 1 个历史基线失败）。
- 文档：`docs/04-API接口说明书.md` 端点表扩充 + 统一成功响应格式。
- ⚠️ PG 实机验证留待环境（PgEventQueryAdapter 需 DATABASE_URL）。

## Acceptance criteria

- [ ] `GET /api/v1/events` — 分页查询风险事件（page/per_page），支持 manufacturer/country/hazard_type 筛选
- [ ] `GET /api/v1/events/{event_id}` — 获取单个事件详情
- [ ] `POST /api/v1/events/assess` — 对传入事件详情实时评分，返回 RiskScore 结果（含 breakdown）
- [ ] `POST /api/v1/events/batch-assess` — 批量评分，最多 100 个，返回结果列表
- [ ] `GET /api/v1/companies/{name}/profile` — 企业风险画像（聚合该企业所有事件+评分）
- [ ] `GET /api/v1/alerts` — 预警列表（分页+状态筛选）
- [ ] `GET /api/v1/alerts/{alert_id}` — 预警详情
- [ ] 统一响应格式：`{"success": true, "data": {...}, "meta": {"request_id": "...", "quota_used": N}, "error": null}`
- [ ] 所有端点租户隔离：只能查到当前 account_id 下的数据

## References

- `docs/技术改造路线图.md` §4.4 REST API 设计
- `docs/04-API接口说明书.md`
