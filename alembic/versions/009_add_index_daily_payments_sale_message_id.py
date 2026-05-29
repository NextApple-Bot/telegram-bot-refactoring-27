"""Add index on daily_payments.sale_message_id

Revision ID: 009
Revises: 008
Create Date: 2026-04-11 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем колонку, если её нет
    op.execute("ALTER TABLE daily_payments ADD COLUMN IF NOT EXISTS sale_message_id BIGINT")
    # Создаём индекс (заворачиваем в IF EXISTS для идемпотентности)
    op.execute("CREATE INDEX IF NOT EXISTS idx_daily_payments_sale_message_id ON daily_payments (sale_message_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_daily_payments_sale_message_id")
    # Колонку не удаляем
