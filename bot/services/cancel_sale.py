"""
Единый контракт отмены продажи.

Используется web_admin/routes/sold.py (одна / все / период).

Гарантирует в рамках уже открытой транзакции:
  1) товар снова в items (serial — только если свободен)
  2) удаление Sale по message_id (или fallback по item_id)
  3) удаление DailyPayment по sale_message_id
  4) удаление записи DeletedItem

Не трогает уведомления в Telegram и clear_adjustments — это зона роута.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import DailyPayment, DeletedItem, Item, Sale

logger = logging.getLogger(__name__)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def cancel_one_deleted_sale(
    session: AsyncSession,
    deleted: DeletedItem,
) -> dict[str, Any]:
    """
    Откат одной продажи по записи DeletedItem.

    Вызывать внутри session.begin().
    Возвращает метаданные для уведомления и сброса корректировок.
    """
    if deleted is None:
        raise ValueError("DeletedItem is None")
    if getattr(deleted, "restored", False):
        raise ValueError("already_restored")

    item_text = deleted.text or ""
    serial = (deleted.serial or "").strip() or None
    sale_message_id = deleted.sale_message_id
    original_item_id = deleted.item_id
    category_id = deleted.category_id
    day_for_adj: date | None = _as_date(deleted.deleted_at)

    # Serial только если ещё не занят на витрине
    if serial:
        exists = await session.scalar(
            select(Item.id).where(Item.serial == serial).limit(1)
        )
        serial_for_item = None if exists else serial
        if exists:
            logger.warning(
                "cancel_sale: serial=%s уже в items — восстанавливаем без serial",
                serial,
            )
    else:
        serial_for_item = None

    session.add(
        Item(
            text=item_text,
            serial=serial_for_item,
            category_id=category_id,
            is_booked=False,
            is_sold=False,
        )
    )

    sales_deleted = 0
    payments_deleted = 0

    if sale_message_id is not None:
        r1 = await session.execute(
            delete(Sale).where(Sale.message_id == sale_message_id)
        )
        sales_deleted = r1.rowcount if r1.rowcount is not None else 0
        r2 = await session.execute(
            delete(DailyPayment).where(
                DailyPayment.sale_message_id == sale_message_id
            )
        )
        payments_deleted = r2.rowcount if r2.rowcount is not None else 0
    elif original_item_id is not None:
        r1 = await session.execute(
            delete(Sale).where(Sale.item_id == original_item_id)
        )
        sales_deleted = r1.rowcount if r1.rowcount is not None else 0

    deleted.restored = True
    await session.delete(deleted)

    logger.info(
        "cancel_one_deleted_sale: deleted_id=%s msg=%s sales=%s payments=%s day=%s",
        getattr(deleted, "id", None),
        sale_message_id,
        sales_deleted,
        payments_deleted,
        day_for_adj,
    )

    return {
        "item_text": item_text,
        "serial": serial,
        "sale_message_id": sale_message_id,
        "day": day_for_adj,
        "sales_deleted": sales_deleted,
        "payments_deleted": payments_deleted,
    }
