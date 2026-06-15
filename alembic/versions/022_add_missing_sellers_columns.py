"""add missing columns to sellers table

Revision ID: 022
Revises: 021
Create Date: 2026-06-15 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '022'
down_revision = '021'          # ← Убедись, что это ID последней миграции у тебя
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем недостающие колонки в таблицу sellers
    op.add_column('sellers', sa.Column('phone', sa.String(length=20), nullable=True))
    op.add_column('sellers', sa.Column('telegram_username', sa.String(length=100), nullable=True))
    op.add_column('sellers', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('sellers', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_column('sellers', 'created_at')
    op.drop_column('sellers', 'is_active')
    op.drop_column('sellers', 'telegram_username')
    op.drop_column('sellers', 'phone')
