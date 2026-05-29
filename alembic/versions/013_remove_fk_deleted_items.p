"""Remove foreign key from deleted_items.item_id

Revision ID: 013
Revises: 012
Create Date: 2026-04-23 05:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Удаляем внешний ключ, если он существует
    op.execute("""
        ALTER TABLE deleted_items 
        DROP CONSTRAINT IF EXISTS deleted_items_item_id_fkey
    """)
    # Создаём индекс для быстрого поиска по item_id
    op.create_index('idx_deleted_items_item_id', 'deleted_items', ['item_id'])


def downgrade() -> None:
    # Восстанавливаем внешний ключ при откате
    op.drop_index('idx_deleted_items_item_id', table_name='deleted_items')
    op.execute("""
        ALTER TABLE deleted_items 
        ADD CONSTRAINT deleted_items_item_id_fkey 
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
    """)
