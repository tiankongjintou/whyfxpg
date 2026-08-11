"""Webhook 服务（P05）。

- 注册 / 查询 / 删除订阅（account_id 下 url 唯一）。
- ``notify(account_id, event_type, payload)``：找出订阅该事件类型的
  Webhook 并投递（HMAC-SHA256 签名，最多重试 3 次指数退避，写投递日志）。
- 签名头：``X-Whyfxpg-Signature: sha256=<hex>`` + ``X-Whyfxpg-Timestamp``
  （timestamp 参与签名，防重放）。
"""

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable

from whyfxpg.ports.webhook_port import WebhookPort, WebhookRecord

# 投递回调：默认 httpx 同步 POST；测试注入 fake
DeliverFn = Callable[[str, dict, str, str], bool]


def _default_deliver(url: str, payload: dict, signature: str, timestamp: str) -> bool:
    import httpx

    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={
                "X-Whyfxpg-Signature": f"sha256={signature}",
                "X-Whyfxpg-Timestamp": timestamp,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        return resp.status_code < 400
    except httpx.HTTPError:
        return False


def sign_payload(secret: str, payload: bytes, timestamp: str) -> str:
    """HMAC-SHA256 签名（secret + timestamp + body）。"""
    message = timestamp.encode("utf-8") + b"\n" + payload
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class WebhookService:
    """Webhook 订阅管理与投递。"""

    MAX_ATTEMPTS = 3

    def __init__(self, port: WebhookPort, deliver: DeliverFn | None = None):
        self._port = port
        self._deliver: DeliverFn = deliver or _default_deliver

    # ── 订阅管理 ──────────────────────────────────────────────

    def register(self, account_id: str, url: str, event_types: list[str]) -> WebhookRecord:
        """注册 Webhook（account_id 下 url 唯一，重复注册更新 secret）。"""
        secret = secrets.token_hex(16)
        return self._port.create_webhook(account_id, url, secret, event_types)

    def list(self, account_id: str) -> list[WebhookRecord]:
        return self._port.list_webhooks(account_id)

    def delete(self, account_id: str, webhook_id: str) -> bool:
        return self._port.delete_webhook(account_id, webhook_id)

    def delete_account_webhooks(self, account_id: str) -> int:
        """账户删除时清理（AC-7）。"""
        return self._port.delete_account_webhooks(account_id)

    # ── 触发与投递 ────────────────────────────────────────────

    def notify(self, account_id: str, event_type: str, payload: dict) -> int:
        """触发事件：投递所有订阅该 event_type 的 Webhook，返回投递数。"""
        delivered = 0
        for webhook in self._port.list_webhooks(account_id):
            if event_type not in webhook.event_types or not webhook.enabled:
                continue
            if self._deliver_webhook(webhook, event_type, payload):
                delivered += 1
        return delivered

    def _deliver_webhook(self, webhook: WebhookRecord, event_type: str, payload: dict) -> bool:
        body = json.dumps(payload, ensure_ascii=False)
        timestamp = str(int(time.time()))
        signature = sign_payload(webhook.secret, body.encode("utf-8"), timestamp)

        last_error: Exception | None = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                ok = self._deliver(webhook.url, payload, signature, timestamp)
            except Exception as exc:  # noqa: BLE001 — 投递失败重试,任何异常都兜底
                last_error = exc
                ok = False
            if ok:
                self._port.log_delivery(webhook.webhook_id, event_type, body, "delivered", attempt)
                return True
            if attempt < self.MAX_ATTEMPTS:
                time.sleep(2 ** attempt)  # 指数退避:2s, 4s
        error_msg = str(last_error or "HTTP 非 2xx")
        self._port.log_delivery(webhook.webhook_id, event_type, body, f"failed: {error_msg}", self.MAX_ATTEMPTS)
        return False
