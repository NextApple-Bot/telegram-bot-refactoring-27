"""Remove system item and category used for booking statistics hack

Revision ID: 021
Revises: 020
Create Date: 2026-06-02 10:55:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Удаляем служебный товар id=0 и категорию __SYSTEM__."""
    # Удаляем служебный товар (если существует)
    op.execute("DELETE FROM items WHERE id = 0")
    
    # Удаляем служебную категорию (если существует)
    op.execute("DELETE FROM categories WHERE name = '__SYSTEM__'")


def downgrade() -> None:
    """Восстанавливаем служебные данные (как было в миграции 017)."""
    # Восстанавливаем категорию __SYSTEM__
    op.execute("""
        INSERT INTO categories (name, sort_order)
        VALUES ('__SYSTEM__', -1)
        ON CONFLICT (name) DO NOTHING;
    """)
    
    # Получаем id категории
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM categories WHERE name = '__SYSTEM__'")
    ).fetchone()
    
    if row:
        sys_cat_id = row[0]
        # Восстанавливаем служебный товар с id = 0
        op.execute(f"""
            INSERT INTO items (id, text, category_id, is_booked)
            VALUES (0, '__SYSTEM_STATS__', {sys_cat_id}, FALSE)
            ON CONFLICT (id) DO NOTHING;
        """)
