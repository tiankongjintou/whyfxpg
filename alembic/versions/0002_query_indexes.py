"""0002: 查询性能索引补全（TD02）

在 0001（多租户）基础上补齐大数据量查询所需索引：

- ``risk_events``: country / product_category（0001 未建），
  manufacturer 已在 0001 建立（此处幂等检查，防止重复建）
- ``alert_records``: 补 ``created_at`` 列 + ``(account_id, created_at)`` 复合索引
  （与 risk_events.created_at 对齐；account_id 租户隔离查询常用前缀）
- ``pipeline_runs``: ``(status, completed_at)`` 索引。该表由数据迁移脚本
  （scripts/migrate_sqlite_to_postgres.py 自动 DDL）创建、非 Alembic 管理，
  故仅在表已存在时创建索引。

幂等性：所有建索引/加列操作均检查存在性，可安全重复执行。
Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    from sqlalchemy import inspect

    return index in {i["name"] for i in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect

    insp = inspect(bind)

    # ── 1. risk_events 查询索引（TD02 AC-1）──────────────────────────
    if not _index_exists(bind, "risk_events", "idx_risk_events_country"):
        op.create_index("idx_risk_events_country", "risk_events", ["country"])
    if not _index_exists(bind, "risk_events", "idx_risk_events_product_category"):
        op.create_index("idx_risk_events_product_category", "risk_events", ["product_category"])
    # manufacturer 索引由 0001 建立：幂等保护，防止重复创建报错
    if not _index_exists(bind, "risk_events", "idx_risk_events_manufacturer"):
        op.create_index("idx_risk_events_manufacturer", "risk_events", ["manufacturer"])

    # ── 2. alert_records：created_at 列 + (account_id, created_at) 索引（TD02 AC-2）
    alert_cols = {c["name"] for c in insp.get_columns("alert_records")}
    if "created_at" not in alert_cols:
        op.add_column(
            "alert_records",
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=True,
                server_default=sa.text("now()"),
            ),
        )
    if not _index_exists(bind, "alert_records", "idx_alert_account_created"):
        op.create_index("idx_alert_account_created", "alert_records", ["account_id", "created_at"])

    # ── 3. pipeline_runs：(status, completed_at) 索引（TD02 AC-3）────
    # 表由数据迁移脚本自动 DDL 创建（非 Alembic 管理），存在才建索引
    if insp.has_table("pipeline_runs") and not _index_exists(
        bind, "pipeline_runs", "idx_pipeline_status_completed"
    ):
        op.create_index(
            "idx_pipeline_status_completed", "pipeline_runs", ["status", "completed_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect

    insp = inspect(bind)

    for table, index in [
        ("risk_events", "idx_risk_events_country"),
        ("risk_events", "idx_risk_events_product_category"),
        ("alert_records", "idx_alert_account_created"),
    ]:
        if _index_exists(bind, table, index):
            op.drop_index(index, table_name=table)

    if insp.has_table("pipeline_runs") and _index_exists(
        bind, "pipeline_runs", "idx_pipeline_status_completed"
    ):
        op.drop_index("idx_pipeline_status_completed", table_name="pipeline_runs")

    alert_cols = {c["name"] for c in insp.get_columns("alert_records")}
    if "created_at" in alert_cols:
        with op.batch_alter_table("alert_records") as batch_op:
            batch_op.drop_column("created_at")
