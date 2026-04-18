"""device custom_id column

Revision ID: b8e4c1a6f2d3
Revises: a7b3c9e2d4f1
Create Date: 2026-04-18 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e4c1a6f2d3"
down_revision: Union[str, None] = "a7b3c9e2d4f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("custom_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "custom_id")
