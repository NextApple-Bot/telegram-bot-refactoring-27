"""Add booking fields to items table

Revision ID: 003
Revises: 002
Create Date: 2026-04-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонки для хранения данных брони
    op.add_column('items', sa.Column('booking_price', sa.Float(), nullable=True))
    op.add_column('items', sa.Column('booking_prepayment', sa.Float(), nullable=True))
    op.add_column('items', sa.Column('booking_platform', sa.String(), nullable=True))
    op.add_column('items', sa.Column('booking_full_name', sa.String(), nullable=True))
    op.add_column('items', sa.Column('booking_phone', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'booking_phone')
    op.drop_column('items', 'booking_full_name')
    op.drop_column('items', 'booking_platform')
    op.drop_column('items', 'booking_prepayment')
    op.drop_column('items', 'booking_price')
