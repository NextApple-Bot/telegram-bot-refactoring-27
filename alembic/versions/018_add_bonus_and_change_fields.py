"""add sale and booking fields (full)

Revision ID: 018
Revises: 017
Create Date: 2026-05-11 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Поля для продажи
    op.add_column('items', sa.Column('sale_price', sa.Numeric(12,2), nullable=True))
    op.add_column('items', sa.Column('sale_prepayment', sa.Numeric(12,2), nullable=True))
    op.add_column('items', sa.Column('sale_payment_amount', sa.Numeric(12,2), nullable=True))
    op.add_column('items', sa.Column('sale_payment_type', sa.String(), nullable=True))
    op.add_column('items', sa.Column('sale_bonus', sa.Numeric(12,2), nullable=True))
    op.add_column('items', sa.Column('sale_change', sa.Numeric(12,2), nullable=True))
    op.add_column('items', sa.Column('sale_change_type', sa.String(), nullable=True))
    op.add_column('items', sa.Column('sale_platform', sa.String(), nullable=True))
    op.add_column('items', sa.Column('sale_full_name', sa.String(), nullable=True))
    op.add_column('items', sa.Column('sale_phone', sa.String(), nullable=True))
    op.add_column('items', sa.Column('is_sold', sa.Boolean(), nullable=False, server_default='false'))

    # Поля для брони
    op.add_column('items', sa.Column('booking_bonus', sa.Numeric(12,2), nullable=True))
    op.add_column('items', sa.Column('booking_bonus_reason', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('items', 'booking_bonus_reason')
    op.drop_column('items', 'booking_bonus')
    op.drop_column('items', 'is_sold')
    op.drop_column('items', 'sale_phone')
    op.drop_column('items', 'sale_full_name')
    op.drop_column('items', 'sale_platform')
    op.drop_column('items', 'sale_change_type')
    op.drop_column('items', 'sale_change')
    op.drop_column('items', 'sale_bonus')
    op.drop_column('items', 'sale_payment_type')
    op.drop_column('items', 'sale_payment_amount')
    op.drop_column('items', 'sale_prepayment')
    op.drop_column('items', 'sale_price')
