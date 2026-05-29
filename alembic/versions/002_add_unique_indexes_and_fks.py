"""Add unique index on serial and foreign keys

Revision ID: 002
Revises: 001
Create Date: 2026-04-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Добавляем полноценный уникальный индекс на serial в items (игнорируя NULL)
    # Сначала удаляем старый частичный индекс, если он существует
    op.execute("DROP INDEX IF EXISTS idx_items_serial_unique")
    # Создаём уникальный индекс, который允许 NULL (в PostgreSQL уникальные индексы позволяют несколько NULL)
    op.create_index('idx_items_serial_unique', 'items', ['serial'], unique=True,
                    postgresql_where=sa.text('serial IS NOT NULL'))

    # 2. Добавляем внешние ключи (если их нет)
    # Проверяем существование FK перед созданием
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    fk_list = [fk['name'] for fk in inspector.get_foreign_keys('sales')]
    if 'sales_item_id_fkey' not in fk_list:
        op.create_foreign_key('sales_item_id_fkey', 'sales', 'items', ['item_id'], ['id'], ondelete='SET NULL')
    
    fk_list = [fk['name'] for fk in inspector.get_foreign_keys('bookings')]
    if 'bookings_item_id_fkey' not in fk_list:
        op.create_foreign_key('bookings_item_id_fkey', 'bookings', 'items', ['item_id'], ['id'], ondelete='SET NULL')
    
    fk_list = [fk['name'] for fk in inspector.get_foreign_keys('deleted_items')]
    if 'deleted_items_category_id_fkey' not in fk_list:
        op.create_foreign_key('deleted_items_category_id_fkey', 'deleted_items', 'categories', ['category_id'], ['id'], ondelete='SET NULL')
    
    # 3. Добавляем индексы для ускорения запросов
    op.create_index('idx_sales_sold_at', 'sales', ['sold_at'])
    op.create_index('idx_preorders_created_at', 'preorders', ['created_at'])
    op.create_index('idx_bookings_booked_at', 'bookings', ['booked_at'])
    op.create_index('idx_clients_phone', 'clients', ['phone'])
    op.create_index('idx_clients_telegram_username', 'clients', ['telegram_username'])
    op.create_index('idx_purchases_client_id', 'purchases', ['client_id'])
    op.create_index('idx_items_category_id', 'items', ['category_id'])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index('idx_items_serial_unique', table_name='items')
    op.drop_index('idx_sales_sold_at', table_name='sales')
    op.drop_index('idx_preorders_created_at', table_name='preorders')
    op.drop_index('idx_bookings_booked_at', table_name='bookings')
    op.drop_index('idx_clients_phone', table_name='clients')
    op.drop_index('idx_clients_telegram_username', table_name='clients')
    op.drop_index('idx_purchases_client_id', table_name='purchases')
    op.drop_index('idx_items_category_id', table_name='items')
    
    # Удаляем внешние ключи (если они были созданы)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    fk_list = [fk['name'] for fk in inspector.get_foreign_keys('sales')]
    if 'sales_item_id_fkey' in fk_list:
        op.drop_constraint('sales_item_id_fkey', 'sales', type_='foreignkey')
    fk_list = [fk['name'] for fk in inspector.get_foreign_keys('bookings')]
    if 'bookings_item_id_fkey' in fk_list:
        op.drop_constraint('bookings_item_id_fkey', 'bookings', type_='foreignkey')
    fk_list = [fk['name'] for fk in inspector.get_foreign_keys('deleted_items')]
    if 'deleted_items_category_id_fkey' in fk_list:
        op.drop_constraint('deleted_items_category_id_fkey', 'deleted_items', type_='foreignkey')
    
    # Восстанавливаем старый частичный индекс (опционально)
    op.create_index('idx_items_serial_unique', 'items', ['serial'], unique=True,
                    postgresql_where=sa.text('serial IS NOT NULL'))
