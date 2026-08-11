# P1b-01 — 账户管理 API(多租户运营闭环)

**What to build:**
在 P02 API Key 认证基础上补齐账户运营端点:企业账户注册(生成 API Key)、
API Key 轮换、账户禁用。解决"P02 只有认证没有账户生命周期管理"的缺口,
让 `scripts/self-hosted/bootstrap_admin.py` 的手动建号流程产品化为 API。

**Blocked by:** P02(认证中间件/AccountService 已有)

**Status:** completed
**Claimed by:** reasonix-agent (2026-08-11)
**Completed:** 2026-08-11

## Resolution (2026-08-11)

- **AC-1** `POST /api/v1/accounts`：X-Master-Key 保护（env `WHYFXPG_MASTER_KEY`，
  未配置 503 / 不匹配 403），创建账户并返回 API Key 明文一次 + prefix。
- **AC-2** `POST /api/v1/account/api-key/rotate`：轮换自身 Key（旧 key 立即作废，
  测试验证旧 403 / 新 200）。
- **AC-3** `POST /api/v1/account/disable`：禁用账户（后续请求 403"账户已停用"）。
- **AC-4** `GET /api/v1/accounts/{account_id}`：租户隔离（仅自身；master key 可查
  任意）；404 语义。
- **AC-5** AccountPort 扩展 4 方法（create/rotate/status/get_by_id），
  InMemory 重构为 hash+id 双索引，Pg 实现 INSERT/UPDATE/SELECT。
- **AC-6** 未配置 master key → 503（测试覆盖）。
- **AC-7** 全量 pytest 341 passed + ruff/mypy 全绿（222 文件）。
- **AC-8** `docs/04` 端点表 + §2.1 Master Key + §2.2 统一 HTTP 错误格式。
- 附带：main.py 补 HTTPException 全局 handler，路由错误（404/403/422）
  统一为 {success, error, request_id} 格式（此前仅中间件错误统一）。
- ⚠️ PgAccountAdapter 实机验证留待环境。

## Acceptance criteria

- [ ] `POST /api/v1/accounts` — 创建账户(company_name, plan_type)
      需 `X-Master-Key` 头(env `WHYFXPG_MASTER_KEY`),成功返回
      api_key(明文仅此一次)+ api_key_prefix + account_id
- [ ] `POST /api/v1/account/api-key/rotate` — 轮换当前账户 API Key
      (旧 key 立即作废,返回新 key 明文一次)
- [ ] `POST /api/v1/account/disable` — 禁用当前账户(后续请求 403)
- [ ] `GET /api/v1/accounts/{account_id}` — 账户详情(需 API Key + 租户隔离,
      仅自身或 master key)
- [ ] AccountPort 扩展:`create_account` / `rotate_api_key` / `set_account_status` /
      `get_account_by_id`;InMemory + Pg 双适配器同步
- [ ] 未配置 `WHYFXPG_MASTER_KEY` 时 POST /accounts 返回 503(拒绝注册)
- [ ] 全量 pytest 通过 + ruff/mypy 无 ERROR
- [ ] 文档更新:`docs/04-API接口说明书.md` 端点表 + §2 认证补充 master key 说明

## References

- `whyfxpg/ports/account_port.py`、`whyfxpg/services/account_service.py`
- `whyfxpg_api/routes/`(P02 路由模式)
- 路线图 §6.3「多租户隔离不完整 — API 层强制注入」
