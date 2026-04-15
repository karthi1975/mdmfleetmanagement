"""rename played_at to received_at

Revision ID: 1bfe55aef871
Revises: 099234203802
Create Date: 2026-04-02 10:42:07.626843

"""
from typing import Sequence, Union

from alembic import op

revision: str = '1bfe55aef871'
down_revision: Union[str, None] = '099234203802'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('broadcast_acks', 'played_at', new_column_name='received_at')


def downgrade() -> None:
    op.alter_column('broadcast_acks', 'received_at', new_column_name='played_at')
