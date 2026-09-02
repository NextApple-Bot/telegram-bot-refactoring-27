"""Drop sales_item_id_fkey — item_id is historical after sale

Revision ID: 029
Revises: 028
Create Date: 2026-09-02

После продажи товар удаляется из items, но sales.item_id остаётся
как историческая ссылка. Жёсткий FK на items ломает запись Sale.

Важно: только DROP CONSTRAINT IF EXISTS — иначе PostgreSQL абортит
транзакцию при отсутствии constraint, и alembic_version не обновляется.
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

    names: set[str] = set()

    for fk in inspector.get_foreign_keys("sales"):
        constrained = fk.get("constrained_columns") or []
        referred = (fk.get("referred_table") or "").lower()
        name = fk.get("name")
        if name and "item_id" in constrained and referred in ("items", "item"):
            names.add(name)

    # Типичные имена на случай, если inspector что-то пропустил
    names.update({"sales_item_id_fkey", "fk_sales_item_id_items"})

    for name in sorted(names):
        # IF EXISTS — не абортит транзакцию, если constraint уже нет
        conn.execute(
            text(f'ALTER TABLE sales DROP CONSTRAINT IF EXISTS "{name}"')
        )


def downgrade() -> None:
    # Не восстанавливаем FK: конфликтует с удалением items после продажи
    pass
