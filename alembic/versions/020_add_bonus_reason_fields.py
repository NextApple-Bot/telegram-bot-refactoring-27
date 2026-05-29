"""Add bonus reason fields to items

Revision ID: 020
Revises: 019
Create Date: 2026-05-11 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '020'
down_revision = '019'   # если последняя 018 – замените на '018'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('items', sa.Column('sale_bonus_reason', sa.String(), nullable=True))
    op.add_column('items', sa.Column('booking_bonus_reason', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('items', 'sale_bonus_reason')
    op.drop_column('items', 'booking_bonus_reason')
