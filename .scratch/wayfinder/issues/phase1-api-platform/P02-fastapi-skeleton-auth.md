# P02 — FastAPI 项目骨架 + 认证中间件

**What to build:**
初始化 FastAPI 项目，建立 API Key 认证中间件和账户验证服务。FastAPI 依赖注入体系、错误处理规范、OpenAPI 文档骨架。

**Blocked by:** P01-sqlite-to-postgresql.md

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1** `whyfxpg_api/` 包（命名与 quality_gate.py 预设一致，ticket 字面
  `api/` 太泛且易与包名冲突）：main.py（create_app 工厂）、dependencies.py、
  routes/（health、me）、models/、schemas/（ErrorResponse、AccountOut）。
- **AC-2** `AuthMiddleware`（`X-API-Key` 头 → `AccountService.verify_key` →
  注入 `request.state.account`）；`RequestIDMiddleware` 在最外层（保证所有
  响应含 X-Request-ID，Auth 403 也能读到 request_id）。
- **AC-3** `AccountService.verify_key(api_key)`：sha256 哈希 → `AccountPort`
  查询（`PgAccountAdapter` 生产 / `InMemoryAccountAdapter` 测试），
  无效或非 active 抛 `ApiKeyError` → 403。
- **AC-4** 统一错误 `{"success": false, "error", "request_id"}`：Auth 403、
  参数校验 422 均使用；`X-Request-ID` 响应头对应。
- **AC-5** OpenAPI 3.0：FastAPI 自动生成，`/docs`（Swagger UI）、`/redoc`。
- **AC-6** 默认保护全部端点，白名单 `/health`、`/docs`、`/redoc`、`/openapi.json`。
- **AC-7** `ruff check whyfxpg_api/` 无 ERROR（quality_gate 自动纳入）。
- 依赖：`fastapi>=0.115` 加入 pyproject（uv.lock 已更新）。
- 测试：`test_api_skeleton.py` 10 个用例（公开端点/403 统一格式/有效 Key/
  request_id/AccountService 语义），全量 pytest 291 passed（仅 1 个历史基线失败）。
- 文档：`docs/04-API接口说明书.md` 新增附录「Phase 1 REST API（FastAPI）」。
- ⚠️ PG 实机验证留待环境：`PgAccountAdapter` 需 DATABASE_URL 指向可用
  PostgreSQL（accounts 表由 P01 Alembic 0001 创建）。

## Acceptance criteria

- [ ] `api/` 目录创建：main.py、dependencies.py、routes/、models/、schemas/
- [ ] API Key 认证中间件：解析 `X-API-Key` 请求头，验证 hash，注入 `request.state.account`
- [ ] `AccountService.verify_key(api_key)` 返回账户信息或 403
- [ ] 统一错误响应格式：`{"success": false, "error": "...", "request_id": "..."}`
- [ ] 自动 OpenAPI 3.0 文档（Swagger UI）可访问
- [ ] 所有端点默认 require API Key（公开端点如 `/health` 除外）
- [ ] 代码检查：ruff check api/ 无 ERROR

## References

- `docs/技术改造路线图.md` §4.1 技术选型 + §4.3 API Gateway 功能
- `docs/04-API接口说明书.md`
