"""device display_name column

Revision ID: a7b3c9e2d4f1
Revises: c1d2e3f4a5b6
Create Date: 2026-04-17 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b3c9e2d4f1"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("display_name", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "display_name")
