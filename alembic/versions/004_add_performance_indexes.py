"""Add performance indexes

Revision ID: 004
Revises: 003
Create Date: 2026-04-06 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Индекс для поиска продаж по товару (JOIN с items)
    op.create_index('idx_sales_item_id', 'sales', ['item_id'])

    # Индекс для фильтрации покупок по дате (админка)
    op.create_index('idx_purchases_created_at', 'purchases', ['created_at'])

    # Индекс для сортировки клиентов по дате обновления
    op.create_index('idx_clients_updated_at', 'clients', ['updated_at'])

    # Индекс для фильтрации ежедневных платежей по типу
    op.create_index('idx_daily_payments_type', 'daily_payments', ['type'])

    # Индекс для ускорения запроса остатков (is_booked = false)
    op.create_index('idx_items_is_booked', 'items', ['is_booked'])

    # Составной индекс для очистки старых обработанных сообщений
    op.create_index('idx_processed_messages_chat_processed', 'processed_messages', ['chat_id', 'processed_at'])


def downgrade() -> None:
    op.drop_index('idx_sales_item_id', table_name='sales')
    op.drop_index('idx_purchases_created_at', table_name='purchases')
    op.drop_index('idx_clients_updated_at', table_name='clients')
    op.drop_index('idx_daily_payments_type', table_name='daily_payments')
    op.drop_index('idx_items_is_booked', table_name='items')
    op.drop_index('idx_processed_messages_chat_processed', table_name='processed_messages')
