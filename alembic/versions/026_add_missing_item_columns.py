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

    existing_columns = [col['name'] for col in inspector.get_columns('items')]

    # === Колонки бронирования ===
    columns_to_add = [
        ("booking_birth_date", sa.String(length=50)),
        ("booking_bonus", sa.Numeric(precision=12, scale=2)),
        # Дополнительно (на всякий случай)
        ("sale_birth_date", sa.String(length=50)),
        ("sale_change_type", sa.String(length=50)),
        ("sale_payment_type", sa.String(length=50)),
        ("sale_platform", sa.String(length=100)),
    ]

    for column_name, column_type in columns_to_add:
        if column_name not in existing_columns:
            op.add_column('items', sa.Column(column_name, column_type, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if not inspector.has_table('items'):
        return

    existing_columns = [col['name'] for col in inspector.get_columns('items')]

    columns_to_drop = [
        "sale_platform",
        "sale_payment_type",
        "sale_change_type",
        "sale_birth_date",
        "booking_bonus",
        "booking_birth_date",
    ]

    for column_name in columns_to_drop:
        if column_name in existing_columns:
            op.drop_column('items', column_name)
