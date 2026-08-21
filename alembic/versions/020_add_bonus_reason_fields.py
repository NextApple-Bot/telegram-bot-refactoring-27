"""Add bonus reason fields to items

Revision ID: 020
Revises: 019
Create Date: 2026-05-11 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing = [col['name'] for col in inspector.get_columns('items')]

    # sale_bonus_reason — новая колонка
    if 'sale_bonus_reason' not in existing:
        op.add_column('items', sa.Column('sale_bonus_reason', sa.String(), nullable=True))

    # booking_bonus_reason уже добавлена в миграции 018 — не добавляем повторно


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing = [col['name'] for col in inspector.get_columns('items')]

    if 'sale_bonus_reason' in existing:
        op.drop_column('items', 'sale_bonus_reason')
    # booking_bonus_reason не трогаем — она принадлежит миграции 018
