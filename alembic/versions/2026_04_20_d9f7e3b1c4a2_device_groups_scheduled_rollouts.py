"""device_groups + scheduled_rollouts

Revision ID: d9f7e3b1c4a2
Revises: b8e4c1a6f2d3
Create Date: 2026-04-20 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9f7e3b1c4a2"
down_revision: Union[str, None] = "b8e4c1a6f2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # device_groups: named, reusable selections
    op.create_table(
        "device_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=64),
            sa.ForeignKey("users.id", name="fk_device_groups_created_by_users"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_groups"),
        sa.UniqueConstraint("name", name="uq_device_groups_name"),
    )

    op.create_table(
        "device_group_members",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["device_groups.id"],
            name="fk_device_group_members_group_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            name="fk_device_group_members_device_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "group_id", "device_id", name="pk_device_group_members"
        ),
    )

    # scheduled_rollouts: OTA fired at a future time
    op.create_table(
        "scheduled_rollouts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "target_version",
            sa.String(length=32),
            sa.ForeignKey(
                "firmware_versions.version",
                name="fk_scheduled_rollouts_target_version",
            ),
            nullable=False,
        ),
        sa.Column(
            "strategy",
            sa.String(length=16),
            server_default="full",
            nullable=False,
        ),
        sa.Column("target_devices", sa.JSON(), nullable=False),
        sa.Column("canary_count", sa.Integer(), nullable=True),
        sa.Column("fire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.String(length=64),
            sa.ForeignKey(
                "users.id", name="fk_scheduled_rollouts_created_by_users"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_rollouts"),
    )
    op.create_index(
        "ix_scheduled_rollouts_pending_fire_at",
        "scheduled_rollouts",
        ["fire_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_rollouts_pending_fire_at", table_name="scheduled_rollouts"
    )
    op.drop_table("scheduled_rollouts")
    op.drop_table("device_group_members")
    op.drop_table("device_groups")
