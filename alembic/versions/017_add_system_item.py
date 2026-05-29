"""add system item for booking statistics

Revision ID: 017
Revises: 016
Create Date: 2026-05-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаём служебную категорию, если её нет
    op.execute("""
        INSERT INTO categories (name, sort_order)
        VALUES ('__SYSTEM__', -1)
        ON CONFLICT (name) DO NOTHING;
    """)
    # Получаем id категории __SYSTEM__
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM categories WHERE name = '__SYSTEM__'")
    ).fetchone()
    if row is None:
        return
    sys_cat_id = row[0]

    # Создаём служебный товар с id = 0, если его нет
    op.execute(f"""
        INSERT INTO items (id, text, category_id, is_booked)
        VALUES (0, '__SYSTEM_STATS__', {sys_cat_id}, FALSE)
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    # Удаляем служебный товар и категорию
    op.execute("DELETE FROM items WHERE id = 0")
    op.execute("DELETE FROM categories WHERE name = '__SYSTEM__'")
