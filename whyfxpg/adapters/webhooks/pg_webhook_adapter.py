"""PostgreSQL Webhook 适配器（P05 生产实现）。

webhooks / webhook_delivery_logs 表由 Alembic 0003 迁移创建。
"""

import json

from sqlalchemy import create_engine, text

from whyfxpg.core.db import get_database_url
from whyfxpg.ports.webhook_port import WebhookPort, WebhookRecord


class PgWebhookAdapter(WebhookPort):
    """基于 SQLAlchemy 的 webhooks 表适配器。"""

    def __init__(self, database_url: str | None = None):
        self._url = database_url or get_database_url()
        self._engine = create_engine(self._url)

    def _to_record(self, row) -> WebhookRecord:
        raw_types = row["event_types"] or ""
        try:
            event_types = json.loads(raw_types) if raw_types.startswith("[") else raw_types.split(",")
        except json.JSONDecodeError:
            event_types = raw_types.split(",")
        return WebhookRecord(
            webhook_id=str(row["webhook_id"]),
            account_id=str(row["account_id"]),
            url=row["url"],
            secret=row["secret"],
            event_types=[t for t in event_types if t],
            enabled=bool(row["enabled"]),
        )

    def create_webhook(
        self, account_id: str, url: str, secret: str, event_types: list[str]
    ) -> WebhookRecord:
        # 唯一约束 uq_webhooks_account_url：已存在则更新
        upsert = text(
            "INSERT INTO webhooks (account_id, url, secret, event_types, enabled) "
            "VALUES (:account_id, :url, :secret, :event_types, true) "
            "ON CONFLICT (account_id, url) DO UPDATE SET "
            "secret = EXCLUDED.secret, event_types = EXCLUDED.event_types, enabled = true "
            "RETURNING webhook_id, account_id, url, secret, event_types, enabled"
        )
        with self._engine.begin() as conn:
            row = conn.execute(
                upsert,
                {
                    "account_id": account_id,
                    "url": url,
                    "secret": secret,
                    "event_types": json.dumps(event_types),
                },
            ).mappings().first()
        return self._to_record(row)

    def list_webhooks(self, account_id: str) -> list[WebhookRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT webhook_id, account_id, url, secret, event_types, enabled "
                    "FROM webhooks WHERE account_id = :account_id ORDER BY created_at"
                ),
                {"account_id": account_id},
            ).mappings()
            return [self._to_record(r) for r in rows]

    def get_webhook(self, webhook_id: str) -> WebhookRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT webhook_id, account_id, url, secret, event_types, enabled "
                    "FROM webhooks WHERE webhook_id = :webhook_id"
                ),
                {"webhook_id": webhook_id},
            ).mappings().first()
        return self._to_record(row) if row else None

    def delete_webhook(self, account_id: str, webhook_id: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM webhooks "
                    "WHERE webhook_id = :webhook_id AND account_id = :account_id"
                ),
                {"webhook_id": webhook_id, "account_id": account_id},
            )
        return result.rowcount > 0

    def delete_account_webhooks(self, account_id: str) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM webhooks WHERE account_id = :account_id"),
                {"account_id": account_id},
            )
        return result.rowcount

    def log_delivery(
        self, webhook_id: str, event_type: str, payload: str, status: str, attempts: int
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO webhook_delivery_logs "
                    "(webhook_id, event_type, payload, status, attempts, last_attempt_at) "
                    "VALUES (:webhook_id, :event_type, :payload, :status, :attempts, now())"
                ),
                {
                    "webhook_id": webhook_id,
                    "event_type": event_type,
                    "payload": payload,
                    "status": status,
                    "attempts": attempts,
                },
            )

    def close(self) -> None:
        self._engine.dispose()
