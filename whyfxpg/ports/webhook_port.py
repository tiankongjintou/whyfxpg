"""Webhook 端口 (P05)。

把“如何持久化 Webhook 订阅与投递日志”与业务逻辑分离。
生产用 PgWebhookAdapter，测试用 InMemoryWebhookAdapter。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WebhookRecord:
    webhook_id: str
    account_id: str
    url: str
    secret: str
    event_types: list[str]
    enabled: bool


class WebhookPort(ABC):
    """Webhook 订阅存储端口。"""

    @abstractmethod
    def create_webhook(
        self, account_id: str, url: str, secret: str, event_types: list[str]
    ) -> WebhookRecord:
        """注册 Webhook（account_id 下 url 唯一）。"""
        raise NotImplementedError

    @abstractmethod
    def list_webhooks(self, account_id: str) -> list[WebhookRecord]:
        """列出账户全部 Webhook。"""
        raise NotImplementedError

    @abstractmethod
    def get_webhook(self, webhook_id: str) -> WebhookRecord | None:
        """按 id 取 Webhook（投递用）。"""
        raise NotImplementedError

    @abstractmethod
    def delete_webhook(self, account_id: str, webhook_id: str) -> bool:
        """删除 Webhook（租户隔离），返回是否删除。"""
        raise NotImplementedError

    @abstractmethod
    def delete_account_webhooks(self, account_id: str) -> int:
        """账户删除时清理其全部 Webhook（AC-7）。"""
        raise NotImplementedError

    @abstractmethod
    def log_delivery(
        self,
        webhook_id: str,
        event_type: str,
        payload: str,
        status: str,
        attempts: int,
    ) -> None:
        """记录一次投递尝试到 webhook_delivery_logs。"""
        raise NotImplementedError
