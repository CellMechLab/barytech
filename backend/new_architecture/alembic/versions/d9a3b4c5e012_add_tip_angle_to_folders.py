"""Add tip_angle to folders experiment metadata

Revision ID: d9a3b4c5e012
Revises: c8f1d2e3a904
Create Date: 2026-07-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d9a3b4c5e012"
down_revision: Union[str, None] = "c8f1d2e3a904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tip_angle", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.drop_column("tip_angle")
