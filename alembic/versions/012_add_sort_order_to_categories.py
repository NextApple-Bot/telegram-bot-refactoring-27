"""Add sort_order to categories

Revision ID: 012
Revises: 011
Create Date: 2026-04-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку sort_order с значением по умолчанию 0
    op.add_column('categories', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    # Создаём индекс для ускорения сортировки
    op.create_index('idx_categories_sort_order', 'categories', ['sort_order'])


def downgrade() -> None:
    op.drop_index('idx_categories_sort_order', table_name='categories')
    op.drop_column('categories', 'sort_order')
