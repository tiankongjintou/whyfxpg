"""0003: Webhook 订阅与投递日志表（P05）

- ``webhooks``：企业客户注册的回调订阅（account_id 租户隔离，
  url 在该账户下唯一，event_types 逗号分隔，secret 用于 HMAC 签名）。
- ``webhook_delivery_logs``：每次投递尝试的审计日志
  （id, webhook_id, event_type, payload, status, attempts, last_attempt_at）。

跨后端兼容（SQLite 测试 / PostgreSQL 生产）。幂等：均检查存在性。

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("webhook_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("event_types", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_webhooks_account"),
        sa.UniqueConstraint("account_id", "url", name="uq_webhooks_account_url"),
    )
    op.create_index("idx_webhooks_account", "webhooks", ["account_id"])

    op.create_table(
        "webhook_delivery_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("webhook_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.webhook_id"], name="fk_delivery_webhook"),
    )
    op.create_index("idx_delivery_webhook_id", "webhook_delivery_logs", ["webhook_id"])


def downgrade() -> None:
    op.drop_index("idx_delivery_webhook_id", table_name="webhook_delivery_logs")
    op.drop_table("webhook_delivery_logs")
    op.drop_index("idx_webhooks_account", table_name="webhooks")
    op.drop_table("webhooks")
