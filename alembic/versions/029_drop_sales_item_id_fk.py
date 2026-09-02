"""Drop sales_item_id_fkey — item_id is historical after sale

Revision ID: 029
Revises: 028
Create Date: 2026-09-02

После продажи товар удаляется из items, но sales.item_id остаётся
как историческая ссылка. Жёсткий FK на items ломает запись Sale.
"""
from alembic import op
from sqlalchemy import inspect, text


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if not inspector.has_table("sales"):
        return

    # Ищем любые FK с sales.item_id → items
    fks = inspector.get_foreign_keys("sales")
    for fk in fks:
        constrained = fk.get("constrained_columns") or []
        referred = (fk.get("referred_table") or "").lower()
        if "item_id" in constrained and referred in ("items", "item"):
            name = fk.get("name")
            if name:
                op.drop_constraint(name, "sales", type_="foreignkey")

    # На всякий случай типичные имена
    for name in ("sales_item_id_fkey", "fk_sales_item_id_items"):
        try:
            op.drop_constraint(name, "sales", type_="foreignkey")
        except Exception:
            pass

    # PostgreSQL: если constraint остался без имени в inspector
    try:
        conn.execute(
            text(
                """
                DO $$ BEGIN
                  IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'sales'
                      AND constraint_type = 'FOREIGN KEY'
                      AND constraint_name = 'sales_item_id_fkey'
                  ) THEN
                    ALTER TABLE sales DROP CONSTRAINT sales_item_id_fkey;
                  END IF;
                END $$;
                """
            )
        )
    except Exception:
        pass


def downgrade() -> None:
    # Не восстанавливаем FK: он конфликтует с удалением items после продажи
    pass
