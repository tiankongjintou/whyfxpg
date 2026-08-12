"""0004: config_objects 表（PG 侧配置存储，P1b-04）

对齐 SQLite 004_config_objects.sql：配置对象版本注册表，供
DbConfigStoreAdapter / ConfigurationAdminService 使用。
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "config_objects",
        sa.Column("object_type", sa.String(64), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="published",
        ),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint(
            "object_type", "object_id", "version_id", name="pk_config_objects"
        ),
    )
    op.create_index(
        "idx_config_objects_lookup",
        "config_objects",
        ["object_type", "object_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_config_objects_version",
        "config_objects",
        ["version_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_config_objects_version", table_name="config_objects")
    op.drop_index("idx_config_objects_lookup", table_name="config_objects")
    op.drop_table("config_objects")
