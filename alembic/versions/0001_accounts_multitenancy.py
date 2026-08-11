"""0001: 多租户基础 — accounts 表 + risk_events/alert_records 租户外键 + 索引

P01 (SQLite → PostgreSQL 多租户迁移) 的第一个 Alembic 迁移。

设计决策：
- 本迁移自包含：在空库上直接创建 accounts、risk_events、alert_records 三张
  多租户核心表（含 account_id 外键）与所需索引，是这三张表在 PostgreSQL 上
  schema 的权威来源（其余历史表由 scripts/migrate_sqlite_to_postgres.py
  自动生成 DDL）。
- 跨后端兼容：使用 SQLAlchemy 通用类型（Uuid/Text/Integer/Float/DateTime），
  可在 PostgreSQL 与 SQLite 上执行（本地测试用 sqlite:// URL 验证）。
- account_id 可空：Phase 0 存量数据迁移后无租户归属，先保留 NULL，
  后续按需回填/收紧。

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. accounts（企业账户表，多租户根）──────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("plan_type", sa.Text(), nullable=False, server_default="trial"),
        sa.Column("api_key_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("api_key_prefix", sa.Text(), nullable=False),
        sa.Column("monthly_quota", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    )

    # ── 2. risk_events（核心数据总线，租户隔离）─────────────────────
    # 与 whyfxpg/migrations/001_init_schema.sql + 003/009 增量对齐，
    # 另加 account_id 外键。
    op.create_table(
        "risk_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("publish_date", sa.Date(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("hs_code", sa.Text(), nullable=True),
        sa.Column("product_category", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("manufacturer", sa.Text(), nullable=True),
        sa.Column("hazard_type", sa.Text(), nullable=True),
        sa.Column("hazard_desc", sa.Text(), nullable=True),
        sa.Column("severity_level", sa.Text(), nullable=True),
        sa.Column("ss_score", sa.Integer(), nullable=True),
        sa.Column("probability_level", sa.Text(), nullable=True),
        sa.Column("ps_score", sa.Integer(), nullable=True),
        sa.Column("country_factor", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("product_factor", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("history_factor", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("evidence_factor", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("causal_factor", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("rs_level", sa.Text(), nullable=True),
        sa.Column("standards", sa.Text(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("config_version", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("review_status", sa.Text(), nullable=True, server_default="auto"),
        sa.Column("extracted_language", sa.VARCHAR(10), nullable=True),  # 009
        sa.Column(
            "created_at",  # P01: 与路线图 §4.2 目标 schema 对齐（现有 SQLite 无此列）
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.Column("account_id", sa.Uuid(), nullable=True),  # P01 租户外键
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_risk_events_account"),
        # 注：001 的 page_id → raw_pages 外键在此省略——raw_pages 由数据迁移脚本
        # 自动 DDL 创建（非 Alembic 管理），SQLite 中该约束默认不强制执行；
        # 如需严格约束可在后续迁移补充（PG 端）。
    )

    # ── 3. alert_records（预警记录，租户隔离）───────────────────────
    # 与 001_init_schema.sql + 005 explanation_json 对齐，另加 account_id。
    op.create_table(
        "alert_records",
        sa.Column("alert_id", sa.Text(), primary_key=True),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column("rule_name", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(), nullable=True),
        sa.Column("object_type", sa.Text(), nullable=True),
        sa.Column("object_value", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("triggered_value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True, server_default="pending"),
        sa.Column("confirmed_by", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("explanation_json", sa.Text(), nullable=True),  # 005
        sa.Column("account_id", sa.Uuid(), nullable=True),  # P01 租户外键
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_alert_records_account"),
    )

    # ── 4. 索引（P01 AC-5）──────────────────────────────────────────
    op.create_index("idx_risk_events_account", "risk_events", ["account_id"])
    op.create_index("idx_risk_events_manufacturer", "risk_events", ["manufacturer"])
    op.create_index("idx_risk_events_created", "risk_events", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_risk_events_created", table_name="risk_events")
    op.drop_index("idx_risk_events_manufacturer", table_name="risk_events")
    op.drop_index("idx_risk_events_account", table_name="risk_events")
    # 回退 0001 的增量：risk_events/alert_records 为 001 历史表，仅移除租户列；
    # batch_alter_table 在 SQLite 上通过重建表处理外键约束，PG 上等同普通 ALTER。
    with op.batch_alter_table("alert_records") as batch_op:
        batch_op.drop_column("account_id")
    with op.batch_alter_table("risk_events") as batch_op:
        batch_op.drop_column("account_id")
        batch_op.drop_column("created_at")
    op.drop_table("accounts")
