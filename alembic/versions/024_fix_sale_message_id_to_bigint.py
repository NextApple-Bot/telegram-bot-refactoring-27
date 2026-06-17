"""Fix sale_message_id columns to BIGINT

Revision ID: 024
Revises: 023
Create Date: 2026-06-17 09:50:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # daily_payments
    op.alter_column(
        'daily_payments', 'sale_message_id',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True
    )

    # deleted_items
    op.alter_column(
        'deleted_items', 'sale_message_id',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True
    )

    # sales
    op.alter_column(
        'sales', 'message_id',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True
    )


def downgrade() -> None:
    op.alter_column('daily_payments', 'sale_message_id', type_=sa.Integer())
    op.alter_column('deleted_items', 'sale_message_id', type_=sa.Integer())
    op.alter_column('sales', 'message_id', type_=sa.Integer())
