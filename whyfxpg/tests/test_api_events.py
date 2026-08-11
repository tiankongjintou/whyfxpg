"""P03: 核心 REST API 端点测试。

用 InMemory adapter 注入数据,验证:
- 事件分页/筛选/详情、实时评分(batch)、企业画像、预警列表/详情;
- 统一响应格式 success/data/meta/error;
- 租户隔离:账户 A 只能查到自己的数据。
"""

import pytest
from fastapi.testclient import TestClient

from whyfxpg.adapters.accounts.in_memory_account_adapter import InMemoryAccountAdapter
from whyfxpg.adapters.events.in_memory_event_query_adapter import (
    InMemoryEventQueryAdapter,
)
from whyfxpg.ports.account_port import AccountInfo
from whyfxpg.ports.event_query_port import AlertRecord, EventRecord
from whyfxpg.services.account_service import hash_api_key
from whyfxpg_api.main import create_app

KEY_A = "key-a"
KEY_B = "key-b"

EVENT_A1 = EventRecord(
    event_id="ev-a1", title="产品A召回", product_name="产品A", brand="品牌A",
    manufacturer="Bosch", country="德国", hazard_type="电击",
    severity_level="严重", total_score=1200.0, rs_level="S", publish_date="2026-05-01",
)
EVENT_A2 = EventRecord(
    event_id="ev-a2", title="产品B警告", product_name="产品B", brand="品牌B",
    manufacturer="Makita", country="日本", hazard_type="火灾",
    severity_level="中等", total_score=600.0, rs_level="L", publish_date="2026-04-01",
)
EVENT_B1 = EventRecord(
    event_id="ev-b1", title="其他企业事件", product_name="产品C", brand="品牌C",
    manufacturer="DeWalt", country="美国", hazard_type="割伤",
    severity_level="轻微", total_score=300.0, rs_level="A", publish_date="2026-03-01",
)
ALERT_A1 = AlertRecord(
    alert_id="al-a1", rule_name="高危事件", severity="S", status="pending",
    triggered_at="2026-05-02", description="高风险事件预警",
)


@pytest.fixture
def client() -> TestClient:
    accounts = InMemoryAccountAdapter(
        {
            hash_api_key(KEY_A): AccountInfo("acct-a", "企业A", "pro", 50000, "active"),
            hash_api_key(KEY_B): AccountInfo("acct-b", "企业B", "pro", 50000, "active"),
        }
    )
    events = InMemoryEventQueryAdapter()
    events.add_event("acct-a", EVENT_A1)
    events.add_event("acct-a", EVENT_A2)
    events.add_event("acct-b", EVENT_B1)
    events.add_alert("acct-a", ALERT_A1)
    app = create_app(account_port=accounts, event_query_port=events)
    return TestClient(app)


def _auth(key: str) -> dict:
    return {"X-API-Key": key}


# ── 事件列表:分页 + 筛选 ─────────────────────────────────────


def test_list_events_paginated(client: TestClient) -> None:
    resp = client.get("/api/v1/events?page=1&per_page=1", headers=_auth(KEY_A))
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["error"] is None
    assert len(body["data"]["items"]) == 1
    assert body["data"]["total"] == 2
    assert body["meta"]["request_id"]


def test_list_events_filtered_by_manufacturer(client: TestClient) -> None:
    resp = client.get("/api/v1/events?manufacturer=Bosch", headers=_auth(KEY_A))
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["manufacturer"] == "Bosch"


def test_list_events_filtered_by_hazard_type(client: TestClient) -> None:
    resp = client.get("/api/v1/events?hazard_type=火灾", headers=_auth(KEY_A))
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["event_id"] == "ev-a2"


# ── 事件详情 ─────────────────────────────────────────────────


def test_get_event_detail(client: TestClient) -> None:
    resp = client.get("/api/v1/events/ev-a1", headers=_auth(KEY_A))
    assert resp.status_code == 200
    assert resp.json()["data"]["event_id"] == "ev-a1"


def test_get_event_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/events/ev-missing", headers=_auth(KEY_A))
    assert resp.status_code == 404


# ── 实时评分 ─────────────────────────────────────────────────


def test_assess_event_returns_breakdown(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/events/assess",
        headers=_auth(KEY_A),
        json={"event": {"severity_level": "严重", "country": "高风险国"}, "causal_factor": 1.2},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["rs_level"] in ("S", "M", "L", "A")
    assert "breakdown" in data
    assert data["breakdown"]["causal_factor"] == 1.2


def test_batch_assess_returns_results(client: TestClient) -> None:
    events = [
        {"event": {"severity_level": "中等"}},
        {"event": {"severity_level": "轻微"}},
    ]
    resp = client.post("/api/v1/events/batch-assess", headers=_auth(KEY_A), json={"events": events})
    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 2


def test_batch_assess_rejects_over_100(client: TestClient) -> None:
    events = [{"event": {"severity_level": "中等"}}] * 101
    resp = client.post("/api/v1/events/batch-assess", headers=_auth(KEY_A), json={"events": events})
    assert resp.status_code == 422


# ── 企业画像 ─────────────────────────────────────────────────


def test_company_profile(client: TestClient) -> None:
    resp = client.get("/api/v1/companies/Bosch/profile", headers=_auth(KEY_A))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["company_name"] == "Bosch"
    assert data["event_count"] == 1
    assert data["avg_score"] == 1200.0


def test_company_profile_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/companies/不存在/profile", headers=_auth(KEY_A))
    assert resp.status_code == 404


# ── 预警 ─────────────────────────────────────────────────────


def test_list_alerts_with_status_filter(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts?status=pending", headers=_auth(KEY_A))
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1
    resp2 = client.get("/api/v1/alerts?status=confirmed", headers=_auth(KEY_A))
    assert resp2.json()["data"]["total"] == 0


def test_get_alert_detail(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts/al-a1", headers=_auth(KEY_A))
    assert resp.status_code == 200
    assert resp.json()["data"]["alert_id"] == "al-a1"


# ── 租户隔离（P03 AC-9）──────────────────────────────────────


def test_tenant_isolation_events(client: TestClient) -> None:
    """账户 B 不应看到账户 A 的事件。"""
    resp = client.get("/api/v1/events", headers=_auth(KEY_B))
    items = resp.json()["data"]["items"]
    assert all(item["event_id"] != "ev-a1" for item in items)
    assert resp.json()["data"]["total"] == 1


def test_tenant_isolation_get_event(client: TestClient) -> None:
    resp = client.get("/api/v1/events/ev-a1", headers=_auth(KEY_B))
    assert resp.status_code == 404


def test_tenant_isolation_alerts(client: TestClient) -> None:
    resp = client.get("/api/v1/alerts", headers=_auth(KEY_B))
    assert resp.json()["data"]["total"] == 0
