"""Add sellers and seller_days tables (idempotent)

Revision ID: 025
Revises: 024
Create Date: 2026-06-17 11:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Создаём таблицу sellers, если её ещё нет
    if not inspector.has_table('sellers'):
        op.create_table(
            'sellers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_sellers_name')
        )

    # Создаём таблицу seller_days, если её ещё нет
    if not inspector.has_table('seller_days'):
        op.create_table(
            'seller_days',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('seller_id', sa.Integer(), nullable=False),
            sa.Column('date', sa.Date(), nullable=False),
            sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('seller_id', 'date', name='uq_seller_date')
        )

        # Индексы
        op.create_index('idx_seller_days_date', 'seller_days', ['date'])
        op.create_index('idx_seller_days_seller_date', 'seller_days', ['seller_id', 'date'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table('seller_days'):
        op.drop_index('idx_seller_days_seller_date', table_name='seller_days')
        op.drop_index('idx_seller_days_date', table_name='seller_days')
        op.drop_table('seller_days')

    if inspector.has_table('sellers'):
        op.drop_table('sellers')
