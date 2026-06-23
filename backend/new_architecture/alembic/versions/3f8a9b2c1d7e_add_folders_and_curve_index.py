"""Add folders table and folder_id/curve_index columns to device_data

Revision ID: 3f8a9b2c1d7e
Revises: 60d5f8caef8b
Create Date: 2026-06-18

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a9b2c1d7e'
down_revision: Union[str, None] = '60d5f8caef8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create the folders table ──────────────────────────────────────────
    # Must be created before device_data is modified so the FK reference resolves.
    op.create_table(
        'folders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        # user_id is non-nullable — every folder must belong to a registered user.
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_folders_id'), 'folders', ['id'], unique=False)
    op.create_index(op.f('ix_folders_user_id'), 'folders', ['user_id'], unique=False)

    # ── 2. Add folder_id and curve_index to device_data ──────────────────────
    # batch_alter_table is required for SQLite because that engine does not
    # support ALTER TABLE ADD COLUMN with FK constraints directly; it recreates
    # the whole table under the hood instead.
    with op.batch_alter_table('device_data', schema=None) as batch_op:
        # Nullable FK — rows saved before folders existed will have NULL here.
        batch_op.add_column(sa.Column('folder_id', sa.Integer(), nullable=True))
        # server_default='0' ensures existing rows get a valid non-null value
        # without requiring a Python-side migration pass over all rows.
        batch_op.add_column(
            sa.Column(
                'curve_index',
                sa.Integer(),
                nullable=False,
                server_default='0',
            )
        )
        batch_op.create_index('ix_device_data_folder_id', ['folder_id'], unique=False)
        # FK constraint so cascade deletes from folders propagate to device_data.
        batch_op.create_foreign_key(
            'fk_device_data_folder_id',
            'folders',
            ['folder_id'],
            ['id'],
        )


def downgrade() -> None:
    # ── Reverse: remove columns from device_data, then drop folders ──────────
    with op.batch_alter_table('device_data', schema=None) as batch_op:
        batch_op.drop_constraint('fk_device_data_folder_id', type_='foreignkey')
        batch_op.drop_index('ix_device_data_folder_id')
        batch_op.drop_column('curve_index')
        batch_op.drop_column('folder_id')

    op.drop_index(op.f('ix_folders_user_id'), table_name='folders')
    op.drop_index(op.f('ix_folders_id'), table_name='folders')
    op.drop_table('folders')
