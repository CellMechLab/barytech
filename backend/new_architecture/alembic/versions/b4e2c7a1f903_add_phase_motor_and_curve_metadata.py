"""Add phase, motor_working to device_data and experiment metadata to folders

Revision ID: b4e2c7a1f903
Revises: 3f8a9b2c1d7e
Create Date: 2026-07-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4e2c7a1f903"
down_revision: Union[str, None] = "3f8a9b2c1d7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Add experiment metadata columns to folders ────────────────────────
    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("velocity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("force_conversion_factor", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("z_conversion_factor", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("spring_constant", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("tip_geometry", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("tip_radius", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("sampling_rate", sa.Float(), nullable=True))

    # ── 2. Add phase and motor_working to device_data ────────────────────────
    with op.batch_alter_table("device_data", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("phase", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("motor_working", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("device_data", schema=None) as batch_op:
        batch_op.drop_column("motor_working")
        batch_op.drop_column("phase")

    with op.batch_alter_table("folders", schema=None) as batch_op:
        batch_op.drop_column("sampling_rate")
        batch_op.drop_column("tip_radius")
        batch_op.drop_column("tip_geometry")
        batch_op.drop_column("spring_constant")
        batch_op.drop_column("z_conversion_factor")
        batch_op.drop_column("force_conversion_factor")
        batch_op.drop_column("velocity")
