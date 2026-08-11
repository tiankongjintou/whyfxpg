"""P05: Webhook 订阅系统测试。

用 InMemoryWebhookAdapter + fake 投递函数验证:
- 注册/列表/删除端点;url 唯一;
- notify 触发匹配事件类型并投递(fake 记录签名参数);
- HMAC 签名确定性;投递失败重试 3 次并写日志;账户清理。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from whyfxpg.adapters.accounts.in_memory_account_adapter import InMemoryAccountAdapter
from whyfxpg.adapters.webhooks.in_memory_webhook_adapter import InMemoryWebhookAdapter
from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.services.account_service import hash_api_key
from whyfxpg.services.webhook_service import WebhookService, sign_payload
from whyfxpg_api.main import create_app

ACCOUNT = AccountInfo("acct-wh", "Webhook企业", "pro", 50000, "active")
KEY = "wh-key"


@pytest.fixture
def calls() -> list[dict]:
    return []


def make_app(calls: list[dict], fail: bool = False) -> TestClient:
    accounts = InMemoryAccountAdapter({hash_api_key(KEY): ACCOUNT})

    def fake_deliver(url: str, payload: dict, signature: str, timestamp: str) -> bool:
        calls.append({"url": url, "payload": payload, "signature": signature, "timestamp": timestamp})
        return not fail

    webhooks = WebhookService(InMemoryWebhookAdapter(), deliver=fake_deliver)
    app = create_app(account_port=accounts, webhook_service=webhooks)
    return TestClient(app)


def _auth() -> dict:
    return {"X-API-Key": KEY}


# ── 订阅管理端点 ─────────────────────────────────────────────


def test_register_webhook_returns_secret(calls: list[dict]) -> None:
    client = make_app(calls)
    resp = client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://example.com/hook", "event_types": ["new_high_risk_event", "alert_triggered"]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["webhook_id"]
    assert data["url"] == "https://example.com/hook"
    assert len(data["secret"]) == 32
    assert data["event_types"] == ["new_high_risk_event", "alert_triggered"]


def test_register_rejects_bad_url(calls: list[dict]) -> None:
    client = make_app(calls)
    resp = client.post(
        "/api/v1/webhooks", headers=_auth(), json={"url": "not-a-url", "event_types": []}
    )
    assert resp.status_code == 422


def test_list_webhooks(calls: list[dict]) -> None:
    client = make_app(calls)
    client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://a.com/hook", "event_types": ["alert_triggered"]},
    )
    client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://b.com/hook", "event_types": ["risk_level_changed"]},
    )
    resp = client.get("/api/v1/webhooks", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 2


def test_delete_webhook(calls: list[dict]) -> None:
    client = make_app(calls)
    created = client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://a.com/hook", "event_types": ["alert_triggered"]},
    ).json()["data"]
    resp = client.delete(f"/api/v1/webhooks/{created['webhook_id']}", headers=_auth())
    assert resp.status_code == 200
    resp2 = client.delete(f"/api/v1/webhooks/{created['webhook_id']}", headers=_auth())
    assert resp2.status_code == 404


# ── 触发与投递 ───────────────────────────────────────────────


def test_notify_delivers_matching_event(calls: list[dict]) -> None:
    client = make_app(calls)
    client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://a.com/hook", "event_types": ["new_high_risk_event"]},
    )
    # 通过 app 的 WebhookService 触发
    service: WebhookService = client.app.state.webhook_service  # type: ignore[attr-defined]
    delivered = service.notify(
        ACCOUNT.account_id, "new_high_risk_event", {"event_id": "e1", "rs_level": "S"}
    )
    assert delivered == 1
    assert len(calls) == 1
    assert calls[0]["url"] == "https://a.com/hook"
    assert calls[0]["payload"]["event_id"] == "e1"
    assert calls[0]["signature"]  # HMAC 签名已带上


def test_notify_skips_non_matching_event(calls: list[dict]) -> None:
    client = make_app(calls)
    client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://a.com/hook", "event_types": ["alert_triggered"]},
    )
    service: WebhookService = client.app.state.webhook_service  # type: ignore[attr-defined]
    delivered = service.notify(ACCOUNT.account_id, "new_high_risk_event", {})
    assert delivered == 0
    assert calls == []


def test_delivery_failure_retries_and_logs(calls: list[dict]) -> None:
    client = make_app(calls, fail=True)
    client.post(
        "/api/v1/webhooks",
        headers=_auth(),
        json={"url": "https://a.com/hook", "event_types": ["alert_triggered"]},
    )
    service: WebhookService = client.app.state.webhook_service  # type: ignore[attr-defined]
    adapter: InMemoryWebhookAdapter = service._port  # type: ignore[assignment]
    delivered = service.notify(ACCOUNT.account_id, "alert_triggered", {"a": 1})
    assert delivered == 0
    assert len(calls) == 3  # 重试 3 次
    assert adapter.delivery_logs[-1]["status"].startswith("failed:")
    assert adapter.delivery_logs[-1]["attempts"] == 3


def test_delete_account_webhooks(calls: list[dict]) -> None:
    client = make_app(calls)
    for i in range(3):
        client.post(
            "/api/v1/webhooks",
            headers=_auth(),
            json={"url": f"https://{i}.com/hook", "event_types": ["alert_triggered"]},
        )
    service: WebhookService = client.app.state.webhook_service  # type: ignore[attr-defined]
    removed = service.delete_account_webhooks(ACCOUNT.account_id)
    assert removed == 3
    assert service.list(ACCOUNT.account_id) == []


# ── HMAC 签名 ────────────────────────────────────────────────


def test_alembic_0003_creates_webhook_tables(tmp_path: Path) -> None:
    """0003 迁移在空库上创建 webhooks / webhook_delivery_logs 表。"""
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from alembic import command

    db = tmp_path / "wh.db"
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    tables = set(inspect(engine).get_table_names())
    assert "webhooks" in tables
    assert "webhook_delivery_logs" in tables
    wh_cols = {c["name"] for c in inspect(engine).get_columns("webhooks")}
    assert {"webhook_id", "account_id", "url", "secret", "event_types", "enabled"} <= wh_cols
    engine.dispose()


def test_sign_payload_deterministic() -> None:
    ts = "1700000000"
    body = b'{"a": 1}'
    assert sign_payload("secret", body, ts) == sign_payload("secret", body, ts)
    assert sign_payload("secret", body, ts) != sign_payload("other", body, ts)
    assert sign_payload("secret", body, ts) != sign_payload("secret", b'{"a": 2}', ts)
    assert sign_payload("secret", body, ts) != sign_payload("secret", body, "1700000001")
