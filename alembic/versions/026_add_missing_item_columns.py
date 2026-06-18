"""Add missing columns to items table

Revision ID: 026
Revises: 025
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table('items'):
        return

    existing = [col['name'] for col in inspector.get_columns('items')]

    # Добавляем только те колонки, которых реально нет
    if 'booking_birth_date' not in existing:
        op.add_column('items', sa.Column('booking_birth_date', sa.String(50), nullable=True))

    if 'booking_bonus' not in existing:
        op.add_column('items', sa.Column('booking_bonus', sa.Numeric(12, 2), nullable=True))

    if 'sale_birth_date' not in existing:
        op.add_column('items', sa.Column('sale_birth_date', sa.String(50), nullable=True))

    if 'sale_change_type' not in existing:
        op.add_column('items', sa.Column('sale_change_type', sa.String(50), nullable=True))

    if 'sale_payment_type' not in existing:
        op.add_column('items', sa.Column('sale_payment_type', sa.String(50), nullable=True))

    if 'sale_platform' not in existing:
        op.add_column('items', sa.Column('sale_platform', sa.String(100), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table('items'):
        return

    existing = [col['name'] for col in inspector.get_columns('items')]

    for col in ['sale_platform', 'sale_payment_type', 'sale_change_type',
                'sale_birth_date', 'booking_bonus', 'booking_birth_date']:
        if col in existing:
            op.drop_column('items', col)
