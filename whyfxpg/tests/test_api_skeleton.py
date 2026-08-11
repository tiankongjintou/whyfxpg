"""P02: FastAPI 骨架 + API Key 认证中间件测试。

用 InMemoryAccountAdapter 注入测试账户,验证:
- /health 与 /docs 公开可访问;
- 受保护端点无 key / 无效 key → 403 统一错误格式(含 request_id);
- 有效 key → 注入 request.state.account 并返回账户信息;
- AccountService.verify_key 语义与哈希算法。
"""

import pytest
from fastapi.testclient import TestClient

from whyfxpg.adapters.accounts.in_memory_account_adapter import InMemoryAccountAdapter
from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.account_service import AccountService, ApiKeyError, hash_api_key
from whyfxpg_api.main import create_app

TEST_API_KEY = "test-key-123"
TEST_HASH = hash_api_key(TEST_API_KEY)

TEST_ACCOUNT = AccountInfo(
    account_id="acct-1",
    company_name="测试企业",
    plan_type="pro",
    monthly_quota=5000,
    status="active",
)


@pytest.fixture
def client() -> TestClient:
    adapter = InMemoryAccountAdapter({TEST_HASH: TEST_ACCOUNT})
    app = create_app(account_port=adapter)
    return TestClient(app)


# ── AC-6: 公开端点 ───────────────────────────────────────────


def test_health_is_public(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_docs_is_public(client: TestClient) -> None:
    resp = client.get("/docs")
    assert resp.status_code == 200


# ── AC-2/AC-6: 受保护端点 ────────────────────────────────────


def test_protected_endpoint_requires_key(client: TestClient) -> None:
    resp = client.get("/api/v1/me")
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False
    assert "X-API-Key" in body["error"]
    assert body["request_id"]


def test_protected_endpoint_rejects_invalid_key(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403
    assert resp.json()["success"] is False


def test_protected_endpoint_accepts_valid_key(client: TestClient) -> None:
    resp = client.get("/api/v1/me", headers={"X-API-Key": TEST_API_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["account_id"] == "acct-1"
    assert body["company_name"] == "测试企业"
    assert body["plan_type"] == "pro"
    # 敏感字段不暴露
    assert "api_key_hash" not in body


# ── AC-4: 统一错误格式 + request_id ──────────────────────────


def test_error_response_has_request_id_and_header(client: TestClient) -> None:
    resp = client.get("/api/v1/me")
    body = resp.json()
    assert resp.headers.get("X-Request-ID")
    assert body["request_id"] == resp.headers["X-Request-ID"]
    assert set(body.keys()) == {"success", "error", "request_id"}


# ── AC-3: AccountService ─────────────────────────────────────


def test_account_service_verify_key_success() -> None:
    adapter = InMemoryAccountAdapter({TEST_HASH: TEST_ACCOUNT})
    service = AccountService(adapter)
    account = service.verify_key(TEST_API_KEY)
    assert account.account_id == "acct-1"


def test_account_service_verify_key_failure() -> None:
    adapter = InMemoryAccountAdapter({TEST_HASH: TEST_ACCOUNT})
    service = AccountService(adapter)
    with pytest.raises(ApiKeyError):
        service.verify_key("wrong-key")


def test_account_service_rejects_disabled_account() -> None:
    disabled = AccountInfo(
        account_id="acct-2", company_name="停用企业", plan_type="trial",
        monthly_quota=100, status="disabled",
    )
    adapter = InMemoryAccountAdapter({hash_api_key("k2"): disabled})
    service = AccountService(adapter)
    with pytest.raises(ApiKeyError):
        service.verify_key("k2")


def test_hash_api_key_is_sha256() -> None:
    assert len(TEST_HASH) == 64
    assert hash_api_key("a") == hash_api_key("a")
    assert hash_api_key("a") != hash_api_key("b")
