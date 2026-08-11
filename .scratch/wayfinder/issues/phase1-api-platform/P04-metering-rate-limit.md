# P04 — 计量计费 + 额度限流

**What to build:**
实现 Redis 计量的 API 限流中间件（QPS、日限额、月限额），以及用量查询 API。实现 `MeteringService`，每次 API 调用扣减额度，enterprise 计划无限额。

**Blocked by:** P02-fastapi-skeleton-auth.md

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1/5** `MeteringService.get_monthly_usage(account_id)` + 每次调用计数
  （月度 INCR + TTL 至月末；enterprise 无限额仍计数）。
- **AC-2/3** `MeteringMiddleware`：月度限额（Trial 100 / Basic 5k / Pro 50k）
  与 QPS 限额（1/5/20），超额返回 429 统一错误格式；enterprise 不限。
- **AC-4** Redis counter +1（`RedisMeteringAdapter`，INCR + EXPIRE nx），
  测试/本地用 `InMemoryMeteringAdapter`。
- **AC-6/7** `GET /api/v1/account/usage`（当月用量）、
  `GET /api/v1/account/quota`（含 reset_at）；用量查询不消耗额度。
- **AC-8** 成功响应 `meta` 注入 `quota_used` / `quota_remaining`
  （`MeteringMiddleware` 写入 request.state，`ok_response` 读取）。
- 数据层：`ports/metering_port.py` + `adapters/metering/` 双适配器；
  `redis` 依赖延迟导入（仅生产路径）。
- 测试：`test_api_metering.py` 11 个用例，全量 pytest 317 passed
  （仅 1 个历史基线失败）。
- 文档：`docs/04-API接口说明书.md` 端点表 + §1.2 计量与限流。
- ⚠️ Redis 实机验证留待环境（RedisMeteringAdapter 需 redis:// 可达）。

## Acceptance criteria

- [ ] `MeteringService.get_monthly_usage(account_id)` — 从 Redis 获取当月累计调用次数
- [ ] 限流中间件：Trial ≤ 100/月、Basic ≤ 5,000/月、Pro ≤ 50,000/月，超额返回 429
- [ ] QPS 限制：Trial 1 req/s、Basic 5 req/s、Pro 20 req/s，超额返回 429
- [ ] Enterprise 计划无额度限制（跳过计量查询）
- [ ] 每次 API 调用后 Redis counter +1（TTL = 当月剩余时间）
- [ ] `GET /api/v1/account/usage` — 返回当月累计用量
- [ ] `GET /api/v1/account/quota` — 返回额度信息（含 reset_at）
- [ ] 响应 `meta` 字段注入 `quota_used` 和 `quota_remaining`

## References

- `docs/技术改造路线图.md` §4.3 限流策略 + §4.4 账户端点
