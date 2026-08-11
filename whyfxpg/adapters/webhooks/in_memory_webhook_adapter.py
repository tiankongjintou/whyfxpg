"""InMemory Webhook 适配器（P05 测试替身）。"""

import uuid

from whyfxpg.ports.webhook_port import WebhookPort, WebhookRecord


class InMemoryWebhookAdapter(WebhookPort):
    """内存存储：key = webhook_id；投递日志追加到列表。"""

    def __init__(self) -> None:
        self._webhooks: dict[str, WebhookRecord] = {}
        self.delivery_logs: list[dict] = []

    def create_webhook(
        self, account_id: str, url: str, secret: str, event_types: list[str]
    ) -> WebhookRecord:
        # account_id 下 url 唯一：重复则更新现有
        for existing in self._webhooks.values():
            if existing.account_id == account_id and existing.url == url:
                record = WebhookRecord(
                    webhook_id=existing.webhook_id,
                    account_id=account_id,
                    url=url,
                    secret=secret,
                    event_types=event_types,
                    enabled=True,
                )
                self._webhooks[record.webhook_id] = record
                return record
        record = WebhookRecord(
            webhook_id=str(uuid.uuid4()),
            account_id=account_id,
            url=url,
            secret=secret,
            event_types=event_types,
            enabled=True,
        )
        self._webhooks[record.webhook_id] = record
        return record

    def list_webhooks(self, account_id: str) -> list[WebhookRecord]:
        return [w for w in self._webhooks.values() if w.account_id == account_id]

    def get_webhook(self, webhook_id: str) -> WebhookRecord | None:
        return self._webhooks.get(webhook_id)

    def delete_webhook(self, account_id: str, webhook_id: str) -> bool:
        record = self._webhooks.get(webhook_id)
        if record is None or record.account_id != account_id:
            return False
        del self._webhooks[webhook_id]
        return True

    def delete_account_webhooks(self, account_id: str) -> int:
        ids = [wid for wid, w in self._webhooks.items() if w.account_id == account_id]
        for wid in ids:
            del self._webhooks[wid]
        return len(ids)

    def log_delivery(
        self, webhook_id: str, event_type: str, payload: str, status: str, attempts: int
    ) -> None:
        self.delivery_logs.append(
            {
                "webhook_id": webhook_id,
                "event_type": event_type,
                "payload": payload,
                "status": status,
                "attempts": attempts,
            }
        )
