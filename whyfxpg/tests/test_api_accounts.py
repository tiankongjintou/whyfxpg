"""P1b-01: 账户管理 API 测试。

用 InMemoryAccountAdapter 验证:
- POST /accounts 需 master key(未配置 503 / 错误 403 / 正确创建返回明文 key);
- GET /accounts/{id} 租户隔离(仅自身,或 master key 可查任意);
- API Key 轮换:旧 key 立即失效,新 key 生效;
- 禁用:后续请求 403;
- AccountService 生命周期单元。
"""

import pytest
from fastapi.testclient import TestClient

from whyfxpg.adapters.accounts.in_memory_account_adapter import InMemoryAccountAdapter
from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.account_service import (
    AccountService,
    MasterKeyError,
    hash_api_key,
)
from whyfxpg_api.main import create_app

MASTER = "test-master-key"
EXISTING_KEY = "existing-key"
EXISTING_ACCOUNT = AccountInfo("acct-1", "既有企业", "pro", 50000, "active")


def make_app(adapter: InMemoryAccountAdapter | None = None) -> TestClient:
    accounts = adapter or InMemoryAccountAdapter({hash_api_key(EXISTING_KEY): EXISTING_ACCOUNT})
    app = create_app(account_port=accounts)
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return make_app()


# ── 注册 ─────────────────────────────────────────────────────


def test_create_account_requires_master_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHYFXPG_MASTER_KEY", MASTER)
    resp = client.post("/api/v1/accounts", json={"company_name": "新企业"})
    assert resp.status_code == 403
    assert "Master-Key" in resp.json()["error"] or "master" in resp.json()["error"].lower()


def test_create_account_without_master_config_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WHYFXPG_MASTER_KEY", raising=False)
    resp = client.post(
        "/api/v1/accounts",
        headers={"X-Master-Key": "anything"},
        json={"company_name": "新企业"},
    )
    assert resp.status_code == 503


def test_create_account_success_returns_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHYFXPG_MASTER_KEY", MASTER)
    resp = client.post(
        "/api/v1/accounts",
        headers={"X-Master-Key": MASTER},
        json={"company_name": "新企业", "plan_type": "pro"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["account_id"]
    assert data["api_key"].startswith("whx_")
    assert data["api_key_prefix"] == data["api_key"][:10]
    assert data["plan_type"] == "pro"

    # 新 key 立即可用于认证
    me = client.get("/api/v1/me", headers={"X-API-Key": data["api_key"]})
    assert me.status_code == 200
    assert me.json()["data"]["company_name"] == "新企业"


def test_create_account_wrong_master_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHYFXPG_MASTER_KEY", MASTER)
    resp = client.post(
        "/api/v1/accounts",
        headers={"X-Master-Key": "wrong"},
        json={"company_name": "新企业"},
    )
    assert resp.status_code == 403


def test_create_account_requires_company_name(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHYFXPG_MASTER_KEY", MASTER)
    resp = client.post(
        "/api/v1/accounts", headers={"X-Master-Key": MASTER}, json={"company_name": ""}
    )
    assert resp.status_code == 422


# ── 账户详情:租户隔离 ───────────────────────────────────────


def test_get_account_detail_own(client: TestClient) -> None:
    resp = client.get("/api/v1/accounts/acct-1", headers={"X-API-Key": EXISTING_KEY})
    assert resp.status_code == 200
    assert resp.json()["data"]["company_name"] == "既有企业"


def test_get_account_detail_other_requires_master(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHYFXPG_MASTER_KEY", MASTER)
    # 无 master key → 403
    resp = client.get("/api/v1/accounts/other-id", headers={"X-API-Key": EXISTING_KEY})
    assert resp.status_code == 403
    # 有 master key → 200(查不存在的也返回 404)
    resp2 = client.get(
        "/api/v1/accounts/other-id",
        headers={"X-API-Key": EXISTING_KEY, "X-Master-Key": MASTER},
    )
    assert resp2.status_code == 404


# ── API Key 轮换 ─────────────────────────────────────────────


def test_rotate_api_key_invalidates_old(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/account/api-key/rotate", headers={"X-API-Key": EXISTING_KEY}
    )
    assert resp.status_code == 200
    new_key = resp.json()["data"]["api_key"]
    assert new_key.startswith("whx_")

    # 旧 key 失效
    old = client.get("/api/v1/me", headers={"X-API-Key": EXISTING_KEY})
    assert old.status_code == 403
    # 新 key 生效
    new = client.get("/api/v1/me", headers={"X-API-Key": new_key})
    assert new.status_code == 200


# ── 禁用 ─────────────────────────────────────────────────────


def test_disable_account_blocks_further_requests(client: TestClient) -> None:
    resp = client.post("/api/v1/account/disable", headers={"X-API-Key": EXISTING_KEY})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "disabled"

    blocked = client.get("/api/v1/me", headers={"X-API-Key": EXISTING_KEY})
    assert blocked.status_code == 403
    assert "停用" in blocked.json()["error"]


# ── AccountService 单元 ──────────────────────────────────────


def test_master_key_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHYFXPG_MASTER_KEY", MASTER)
    AccountService.check_master_key(MASTER)  # 不抛
    with pytest.raises(MasterKeyError):
        AccountService.check_master_key("wrong")


def test_master_key_check_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHYFXPG_MASTER_KEY", raising=False)
    with pytest.raises(MasterKeyError):
        AccountService.check_master_key(MASTER)


def test_create_account_service_returns_key() -> None:
    service = AccountService(InMemoryAccountAdapter())
    account, api_key = service.create_account("服务创建", "trial", 100)
    assert account.status == "active"
    assert api_key.startswith("whx_")
    # 新 key 可认证
    assert service.verify_key(api_key).account_id == account.account_id


def test_disable_account_service() -> None:
    service = AccountService(InMemoryAccountAdapter())
    account, api_key = service.create_account("服务禁用", "trial", 100)
    service.disable_account(account.account_id)
    from whyfxpg.services.account_service import ApiKeyError

    with pytest.raises(ApiKeyError):
        service.verify_key(api_key)
