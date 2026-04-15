"""provisioning: device columns + provision_jobs table

Revision ID: c1d2e3f4a5b6
Revises: ab801f1d0c2f
Create Date: 2026-04-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "ab801f1d0c2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("device_type", sa.String(length=32), nullable=False, server_default="room_sensor"),
    )
    op.add_column(
        "devices",
        sa.Column("provision_token", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("target_firmware_version", sa.String(length=32), nullable=True),
    )
    op.alter_column("devices", "mac", existing_type=sa.String(length=17), nullable=True)
    op.alter_column(
        "devices", "firmware_version", existing_type=sa.String(length=32), nullable=True
    )

    op.create_table(
        "provision_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("device_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("firmware_path", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provision_jobs")),
    )
    op.create_index(
        op.f("ix_provision_jobs_device_id"), "provision_jobs", ["device_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_provision_jobs_device_id"), table_name="provision_jobs")
    op.drop_table("provision_jobs")
    op.drop_column("devices", "target_firmware_version")
    op.drop_column("devices", "provision_token")
    op.drop_column("devices", "device_type")
