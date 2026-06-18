"""Add missing columns to items table (booking_birth_date, booking_bonus, sale_birth_date)

Revision ID: 026
Revises: 025
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Проверяем, что таблица items существует
    if not inspector.has_table('items'):
        return

    existing_columns = [col['name'] for col in inspector.get_columns('items')]

    # Добавляем booking_birth_date
    if 'booking_birth_date' not in existing_columns:
        op.add_column('items', sa.Column('booking_birth_date', sa.String(length=50), nullable=True))

    # Добавляем booking_bonus
    if 'booking_bonus' not in existing_columns:
        op.add_column('items', sa.Column('booking_bonus', sa.Numeric(precision=12, scale=2), nullable=True))

    # Добавляем sale_birth_date
    if 'sale_birth_date' not in existing_columns:
        op.add_column('items', sa.Column('sale_birth_date', sa.String(length=50), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table('items'):
        return

    existing_columns = [col['name'] for col in inspector.get_columns('items')]

    if 'sale_birth_date' in existing_columns:
        op.drop_column('items', 'sale_birth_date')
    if 'booking_bonus' in existing_columns:
        op.drop_column('items', 'booking_bonus')
    if 'booking_birth_date' in existing_columns:
        op.drop_column('items', 'booking_birth_date')
