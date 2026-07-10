"""Add sensor_type to folders experiment metadata

Revision ID: c8f1d2e3a904
Revises: b4e2c7a1f903
Create Date: 2026-07-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "c8f1d2e3a904"
down_revision: Union[str, None] = "b4e2c7a1f903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sensor_type", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.drop_column("sensor_type")
