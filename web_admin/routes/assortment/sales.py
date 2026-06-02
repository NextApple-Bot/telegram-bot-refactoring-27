import asyncio
import logging
import uuid
from datetime import date
from typing import Any, Optional, TypedDict

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import DailyPayment, DeletedItem, Item, Sale
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from bot.services.cache import cache

from .notifications import send_sale_notification

logger = logging.getLogger(__name__)


class AccessoryData(TypedDict, total=False):
    """Структура данных об одном аксессуаре при продаже из админки."""
    name: str
    serial: Optional[str]
    price: float
    payment_type: Optional[str]


def generate_sale_message_id() -> int:
    """Генерирует уникальный message_id для связки платежей и deleted_items."""
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF


async def process_accessories(
    session,
    accessories: list[dict[str, Any]],
    sale_message_id: int,
) -> tuple[list[dict[str, Any]], dict[str, float], float]:
    """
    Обрабатывает список аксессуаров:
    - Ищет товары по серийному номеру и удаляет их
    - Создаёт записи в deleted_items
    - Возвращает обработанные аксессуары + агрегированные платежи + общую сумму
    """
    processed: list[dict[str, Any]] = []
    accessories_payments: dict[str, float] = {}
    accessories_total = 0.0

    for acc in accessories:
        acc_price = float(acc.get("price", 0) or 0)
        if acc_price <= 0:
            continue

        accessories_total += acc_price
        display_text = acc.get("name", "").strip() or "Аксессуар"

        serial = acc.get("serial")
        if serial:
            normalized_serial = serial.strip().upper()
            item_info = (
                await session.execute(
                    select(Item).where(func.upper(Item.serial) == normalized_serial)
                )
            ).scalar_one_or_none()

            if item_info:
                display_text = item_info.text
                deleted = DeletedItem(
                    item_id=item_info.id,
                    text=item_info.text,
                    serial=item_info.serial,
                    category_id=item_info.category_id,
                    reason="sale_from_admin",
                    sale_message_id=sale_message_id,
                )
                session.add(deleted)
                await session.delete(item_info)

        payment_type = acc.get("payment_type")
        if payment_type and payment_type != "paid" and acc_price > 0:
            accessories_payments[payment_type] = (
                accessories_payments.get(payment_type, 0) + acc_price
            )

        processed.append({
            "text": display_text,
            "price": acc_price,
            "payment_type": payment_type,
        })

    return processed, accessories_payments, accessories_total


async def create_daily_payments(
    session,
    all_payments: dict[str, float],
    sale_message_id: int,
) -> None:
    """Создаёт записи в daily_payments по агрегированным платежам."""
    for pay_type, amount in all_payments.items():
        if amount > 0:
            payment = DailyPayment(
                type="sale",
                payment_type=pay_type,
                amount=amount,
                sale_message_id=sale_message_id,
            )
            session.add(payment)


async def handle_sale_from_form(
    item_id: int,
    text: str,
    serial: Optional[str],
    category_id: int,
    old_text: str,
    old_serial: str,
    old_category_id: int,
    sale_price
