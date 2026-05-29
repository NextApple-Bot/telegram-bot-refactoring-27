"""Add composite index on items for faster filtering and sorting

Revision ID: 005
Revises: 004
Create Date: 2026-04-10 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'idx_items_category_booked_created',
        'items',
        ['category_id', 'is_booked', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('idx_items_category_booked_created', table_name='items')
