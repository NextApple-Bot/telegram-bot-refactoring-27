"""Add sellers and seller_days tables

Revision ID: 014
Revises: 012
Create Date: 2026-04-27 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014'
down_revision = '012'      # <--- ИСПРАВЛЕНО: было '013', но 013 отсутствует
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sellers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.UniqueConstraint('name')
    )
    op.create_table(
        'seller_days',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('seller_id', sa.Integer(), sa.ForeignKey('sellers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.UniqueConstraint('seller_id', 'date', name='uq_seller_date')
    )
    op.create_index('idx_seller_days_date', 'seller_days', ['date'])


def downgrade() -> None:
    op.drop_index('idx_seller_days_date', table_name='seller_days')
    op.drop_table('seller_days')
    op.drop_table('sellers')
