# P05 — Webhook 订阅系统

**What to build:**
实现企业客户 Webhook 注册、查询、删除功能，以及事件触发回调（HMAC 签名防伪造）。Webhook 触发场景：new_high_risk_event、risk_level_changed、alert_triggered。

**Blocked by:** P03-core-rest-api.md

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1~3** `POST/GET/DELETE /api/v1/webhooks`：注册（account_id 下 url
  唯一，返回 secret 供验签）、列表、删除（404 语义）。
- **AC-4** 触发场景由 `WebhookService.notify(account_id, event_type, payload)`
  提供（new_high_risk_event / risk_level_changed / alert_triggered），
  仅投递订阅匹配事件类型的 Webhook。
- **AC-5** HMAC-SHA256 签名：`X-Whyfxpg-Signature` + `X-Whyfxpg-Timestamp`
  （timestamp+body 参与签名，防篡改/防重放）。
- **AC-6** `webhook_delivery_logs` 表（Alembic 0003）+ 每次投递日志
  （status/attempts）；失败重试最多 3 次指数退避（2s/4s）。
- **AC-7** `WebhookService.delete_account_webhooks(account_id)` 账户清理。
- 数据层：`ports/webhook_port.py` + `adapters/webhooks/` Pg/InMemory 双适配器。
- 测试：`test_api_webhooks.py` 10 个用例（CRUD/触发匹配/签名/重试日志/
  清理/0003 迁移），全量 pytest 327 passed（仅 1 个历史基线失败）。
- 文档：`docs/04-API接口说明书.md` §1.3 Webhook 通知。
- ⚠️ PG 实机验证留待环境（PgWebhookAdapter 需 DATABASE_URL）。

## Acceptance criteria

- [ ] `POST /api/v1/webhooks` — 注册 Webhook URL（account_id 下唯一）
- [ ] `GET /api/v1/webhooks` — 返回当前账户所有已注册 Webhook
- [ ] `DELETE /api/v1/webhooks/{webhook_id}` — 删除指定 Webhook
- [ ] Webhook 触发场景：S/M 级新风险事件、风险等级变化、预警触发
- [ ] HMAC-SHA256 签名：`X-Whyfxpg-Signature: sha256=<hmac_hex>` 请求头
- [ ] Webhook 投递失败时重试机制（最多 3 次，指数退避）
- [ ] Webhook 投递日志表 `webhook_delivery_logs`：id, webhook_id, event_type, payload, status, attempts, last_attempt_at
- [ ] 账户删除时自动清理该账户所有 Webhook

## References

- `docs/技术改造路线图.md` §4.5 Webhook 设计
