"""Add performance indexes for dashboard and payment parsing

Revision ID: 007
Revises: 006
Create Date: 2026-04-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ИСПРАВЛЕНИЕ #2: добавляем расширение pg_trgm перед созданием GIN индекса
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Индекс для быстрой агрегации по дням и типам оплаты
    op.create_index(
        'idx_daily_payments_created_type',
        'daily_payments',
        ['created_at', 'payment_type']
    )
    # Покрывающий индекс для запросов выручки из sales
    op.create_index(
        'idx_sales_sold_at_cover',
        'sales',
        ['sold_at'],
        postgresql_include=['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']
    )
    # Дополнительный индекс для поиска по тексту товара (ускорение умного поиска)
    op.create_index(
        'idx_items_text_gin',
        'items',
        ['text'],
        postgresql_using='gin',
        postgresql_ops={'text': 'gin_trgm_ops'}
    )


def downgrade() -> None:
    op.drop_index('idx_daily_payments_created_type', table_name='daily_payments')
    op.drop_index('idx_sales_sold_at_cover', table_name='sales')
    op.drop_index('idx_items_text_gin', table_name='items')
    # Расширение pg_trgm не удаляем, так как оно может использоваться другими индексами
