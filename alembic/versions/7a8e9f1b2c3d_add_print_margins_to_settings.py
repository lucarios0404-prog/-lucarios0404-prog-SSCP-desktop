"""add print margins to settings

Revision ID: 7a8e9f1b2c3d
Revises: 26d8cc26d7df
Create Date: 2026-09-29 11:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8e9f1b2c3d'
down_revision: Union[str, Sequence[str], None] = '26d8cc26d7df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('print_margin_top', sa.Float(), server_default='15.0', nullable=True))
        batch_op.add_column(sa.Column('print_margin_bottom', sa.Float(), server_default='15.0', nullable=True))
        batch_op.add_column(sa.Column('print_margin_left', sa.Float(), server_default='20.0', nullable=True))
        batch_op.add_column(sa.Column('print_margin_right', sa.Float(), server_default='15.0', nullable=True))
        batch_op.add_column(sa.Column('print_paper_size', sa.String(), server_default='Letter', nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('print_paper_size')
        batch_op.drop_column('print_margin_right')
        batch_op.drop_column('print_margin_left')
        batch_op.drop_column('print_margin_bottom')
        batch_op.drop_column('print_margin_top')
