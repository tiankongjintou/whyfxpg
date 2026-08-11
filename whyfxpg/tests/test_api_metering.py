"""P04: 计量计费 + 额度限流测试。

用 InMemoryMeteringAdapter 验证:
- MeteringService:月度额度消耗/超额、QPS 超限、enterprise 无限额;
- API 层:usage/quota 端点、响应 meta 注入 quota_used/quota_remaining、
  usage 端点不消耗额度。
"""

import pytest
from fastapi.testclient import TestClient

from whyfxpg.adapters.accounts.in_memory_account_adapter import InMemoryAccountAdapter
from whyfxpg.adapters.metering.in_memory_metering_adapter import InMemoryMeteringAdapter
from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.account_service import hash_api_key
from whyfxpg.services.metering_service import MeteringService, QuotaExceeded, month_key
from whyfxpg_api.main import create_app

TRIAL = AccountInfo("acct-trial", "试用企业", "trial", 100, "active")
ENTERPRISE = AccountInfo("acct-ent", "大客户", "enterprise", 0, "active")


def make_service() -> MeteringService:
    return MeteringService(InMemoryMeteringAdapter())


# ── MeteringService 单元 ─────────────────────────────────────


def test_check_and_consume_increments_usage() -> None:
    service = make_service()
    result = service.check_and_consume(TRIAL)
    assert result.quota_used == 1
    assert result.quota_remaining == 99


def test_monthly_quota_exceeded() -> None:
    adapter = InMemoryMeteringAdapter()
    service = MeteringService(adapter)
    # 预置 99 次月度计数（避免被 QPS 限制干扰）
    for _ in range(99):
        adapter.increment_monthly(TRIAL.account_id, month_key(), 3600)
    service.check_and_consume(TRIAL)  # 第 100 次 → OK
    with pytest.raises(QuotaExceeded):
        service.check_and_consume(TRIAL)  # 第 101 次 → 超限


def test_qps_limit_exceeded() -> None:
    service = make_service()
    service.check_and_consume(TRIAL)  # 第 1 次同秒 OK
    with pytest.raises(QuotaExceeded):  # 第 2 次同秒(qps=1)→ 超限
        service.check_and_consume(TRIAL)


def test_enterprise_unlimited() -> None:
    service = make_service()
    for _ in range(5):
        result = service.check_and_consume(ENTERPRISE)
    assert result.quota_remaining is None


def test_get_monthly_usage() -> None:
    service = make_service()
    service.check_and_consume(ENTERPRISE)  # enterprise 无 QPS 限制
    service.check_and_consume(ENTERPRISE)
    assert service.get_monthly_usage(ENTERPRISE.account_id) == 2


def test_get_quota_contains_reset_at() -> None:
    service = make_service()
    quota = service.get_quota(TRIAL)
    assert quota["monthly_limit"] == 100
    assert quota["monthly_used"] == 0
    assert "reset_at" in quota
    assert quota["plan_type"] == "trial"


# ── API 层 ──────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    accounts = InMemoryAccountAdapter(
        {
            hash_api_key("trial-key"): TRIAL,
            hash_api_key("ent-key"): ENTERPRISE,
        }
    )
    app = create_app(account_port=accounts, metering_service=make_service())
    return TestClient(app)


def test_api_meta_injects_quota(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"X-API-Key": "trial-key"})
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["quota_used"] == 1
    assert meta["quota_remaining"] == 99


def test_api_usage_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/account/usage", headers={"X-API-Key": "trial-key"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["monthly_used"] == 0  # usage 查询不消耗额度
    assert data["plan_type"] == "trial"


def test_api_usage_does_not_consume_quota(client: TestClient) -> None:
    headers = {"X-API-Key": "trial-key"}
    for _ in range(3):
        client.get("/api/v1/account/usage", headers=headers)
    resp = client.get("/api/v1/account/usage", headers=headers)
    assert resp.json()["data"]["monthly_used"] == 0


def test_api_quota_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/account/quota", headers={"X-API-Key": "trial-key"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["monthly_limit"] == 100
    assert "reset_at" in data
    assert data["qps_limit"] == 1


def test_api_monthly_quota_exceeded_429(client: TestClient) -> None:
    adapter = InMemoryMeteringAdapter()
    # 预置 trial 账户 100 次月度计数，下一次 API 调用即超限（绕过 QPS 干扰）
    for _ in range(100):
        adapter.increment_monthly(TRIAL.account_id, month_key(), 3600)
    service = MeteringService(adapter)
    accounts = InMemoryAccountAdapter({hash_api_key("trial-key"): TRIAL})
    app = create_app(account_port=accounts, metering_service=service)
    tc = TestClient(app)
    resp = tc.get("/api/v1/me", headers={"X-API-Key": "trial-key"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["success"] is False
    assert "额度" in body["error"]
    assert body["request_id"]
