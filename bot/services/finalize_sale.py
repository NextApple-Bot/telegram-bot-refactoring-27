"""
Единая финализация продажи в БД.

Используется:
  - топик Sales (после поиска товара по SN/тексту)
  - админка (после расчёта формы)

Гарантирует:
  - Sale с разбивкой оплат и message_id (сначала, пока item ещё в БД / без FK)
  - DailyPayment с sale_message_id
  - DeletedItem + удаление Item
  - уникальный message_id при нескольких товарах в одном сообщении

Важно: sales.item_id — историческая ссылка, FK на items быть не должно
(товар после продажи удаляется из витрины).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import DailyPayment, DeletedItem, Item, Sale
from bot.services.assortment import AssortmentService

logger = logging.getLogger(__name__)

PAYMENT_TYPES = ("cash", "terminal", "qr", "transfer", "invoice", "installment")


def normalize_payments(payments: dict[str, float] | None) -> dict[str, float]:
    out = {k: 0.0 for k in PAYMENT_TYPES}
    if not payments:
        return out
    for k, v in payments.items():
        key = (k or "").strip().lower()
        if key in out:
            try:
                out[key] = max(0.0, float(v or 0))
            except (TypeError, ValueError):
                out[key] = 0.0
    return out


def unique_sale_message_id(base_message_id: int, index: int = 0) -> int:
    """
    Sale.message_id UNIQUE.
    Первому товару — исходный Telegram message_id,
    остальным — синтетический id, чтобы не конфликтовать.
    """
    base = int(base_message_id)
    if index <= 0:
        return base
    return base * 1_000_000 + int(index)


async def finalize_item_sale(
    session: AsyncSession,
    *,
    item_id: int,
    item_text: str,
    item_serial: str | None,
    category_id: int | None,
    message_id: int,
    payments: dict[str, float] | None = None,
    reason: str = "sale",
    is_accessory: bool | None = None,
    delete_item: bool = True,
    write_payments: bool = True,
) -> dict[str, Any]:
    """
    Пишет одну продажу в рамках уже открытой SQLAlchemy-сессии/транзакции.

    Порядок:
      1) Sale + DailyPayment
      2) DeletedItem + DELETE Item

    write_payments=False — если платежи уже записаны на другой item
    того же сообщения (мульти-SN: только первый несёт оплаты).

    is_accessory:
      - True/False — явное значение
      - None — авто: True, если у товара нет серийного номера
    """
    pays = normalize_payments(payments if write_payments else None)

    # Снимок данных товара до удаления
    item = await session.get(Item, item_id)
    text = item_text
    serial = item_serial
    cat_id = category_id
    if item is not None:
        text = item.text or text
        serial = item.serial if item.serial is not None else serial
        cat_id = item.category_id if item.category_id is not None else cat_id

    # Аксессуар = товар без серийного номера
    if is_accessory is None:
        is_accessory = not bool((serial or "").strip())

    # 1) Sale — item_id хранится как история (FK на items снят миграцией 029)
    existing = await session.scalar(
        select(Sale.id).where(Sale.message_id == message_id).limit(1)
    )
    if existing:
        logger.warning(
            "Sale с message_id=%s уже есть (id=%s) — пропуск записи Sale",
            message_id,
            existing,
        )
    else:
        session.add(
            Sale(
                item_id=item_id,
                count=1,
                cash=pays["cash"],
                terminal=pays["terminal"],
                qr=pays["qr"],
                transfer=pays["transfer"],
                invoice=pays["invoice"],
                installment=pays["installment"],
                is_accessory=bool(is_accessory),
                message_id=message_id,
            )
        )

    if write_payments:
        for pt, amount in pays.items():
            if amount > 0:
                session.add(
                    DailyPayment(
                        type="sale",
                        payment_type=pt,
                        amount=amount,
                        sale_message_id=message_id,
                    )
                )

    # Flush до DELETE, чтобы INSERT sales ушёл раньше удаления item
    await session.flush()

    # 2) Снять с витрины
    if delete_item:
        if item is not None:
            session.add(
                DeletedItem(
                    item_id=item.id,
                    text=text,
                    serial=serial,
                    category_id=cat_id,
                    reason=reason,
                    sale_message_id=message_id,
                )
            )
            await session.delete(item)
        else:
            session.add(
                DeletedItem(
                    item_id=item_id,
                    text=text,
                    serial=serial,
                    category_id=cat_id,
                    reason=reason,
                    sale_message_id=message_id,
                )
            )

    logger.info(
        "finalize_item_sale: item_id=%s msg=%s accessory=%s payments=%s reason=%s",
        item_id,
        message_id,
        is_accessory,
        pays if write_payments else "(deferred)",
        reason,
    )
    return {
        "item_id": item_id,
        "message_id": message_id,
        "payments": pays,
        "is_accessory": bool(is_accessory),
    }


async def invalidate_sale_caches() -> None:
    try:
        from datetime import date

        from bot.services.cache import cache

        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
    except Exception:
        logger.debug("cache delete dashboard failed", exc_info=True)
    try:
        await AssortmentService.invalidate_cache()
    except Exception:
        logger.debug("assortment cache invalidate failed", exc_info=True)
