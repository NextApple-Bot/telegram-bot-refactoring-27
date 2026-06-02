# web_admin/routes/assortment/sales.py
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
    """Структура одного аксессуара при продаже из админки."""
    name: str
    serial: Optional[str]
    price: float
    payment_type: Optional[str]


def generate_sale_message_id() -> int:
    """Уникальный ID для связки платежей и deleted_items."""
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF


async def process_accessories(
    session,
    accessories: list[dict[str, Any]],
    sale_message_id: int,
) -> tuple[list[dict[str, Any]], dict[str, float], float]:
    """Обрабатывает аксессуары: поиск по серийнику, создание DeletedItem, удаление из items."""
    processed: list[dict[str, Any]] = []
    accessories_payments: dict[str, float] = {}
    accessories_total = 0.0

    for acc in accessories:
        price = float(acc.get("price", 0) or 0)
        if price <= 0:
            continue

        accessories_total += price
        display_text = acc.get("name", "").strip() or "Аксессуар"

        serial = acc.get("serial")
        if serial:
            normalized = serial.strip().upper()
            item_info = (await session.execute(
                select(Item).where(func.upper(Item.serial) == normalized)
            )).scalar_one_or_none()

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

        pay_type = acc.get("payment_type")
        if pay_type and pay_type != "paid" and price > 0:
            accessories_payments[pay_type] = accessories_payments.get(pay_type, 0) + price

        processed.append({
            "text": display_text,
            "price": price,
            "payment_type": pay_type,
        })

    return processed, accessories_payments, accessories_total


async def create_daily_payments(
    session,
    all_payments: dict[str, float],
    sale_message_id: int,
) -> None:
    """Сохраняет все платежи в daily_payments."""
    for pay_type, amount in all_payments.items():
        if amount > 0:
            session.add(DailyPayment(
                type="sale",
                payment_type=pay_type,
                amount=amount,
                sale_message_id=sale_message_id,
            ))


async def handle_sale_from_form(
    item_id: int,
    text: str,
    serial: Optional[str],
    category_id: int,
    old_text: str,
    old_serial: str,
    old_category_id: int,
    sale_price: float,
    sale_prepayment: float = 0.0,
    sale_payment_amount: float = 0.0,
    sale_payment_type: str = "cash",
    sale_platform: Optional[str] = None,
    sale_full_name: Optional[str] = None,
    sale_phone: Optional[str] = None,
    sale_birth_date: Optional[str] = None,
    sale_bonus: Optional[float] = None,
    sale_change: Optional[float] = None,
    sale_change_type: Optional[str] = None,
    accessories: Optional[list[dict[str, Any]]] = None,
    conn=None,
) -> dict[str, Any]:
    """Полноценная продажа товара из админки (полностью соответствует v26)."""
    accessories = accessories or []

    if not sale_price or sale_price <= 0:
        return {"error": "Укажите стоимость продажи"}

    if sale_payment_type != "paid" and (not sale_payment_amount or sale_payment_amount <= 0):
        return {"error": "Укажите сумму оплаты"}

    sale_message_id = generate_sale_message_id()
    own_session = False

    if conn is None:
        async_session = get_async_session_factory()
        session = async_session()
        own_session = True
    else:
        session = conn

    try:
        if own_session:
            await session.begin()

        # 1. Обработка аксессуаров
        processed_accessories, accessories_payments, accessories_total = await process_accessories(
            session, accessories, sale_message_id
        )

        # 2. Агрегация всех платежей
        all_payments: dict[str, float] = dict(accessories_payments)
        if sale_payment_type != "paid" and sale_payment_amount > 0:
            all_payments[sale_payment_type] = all_payments.get(sale_payment_type, 0) + sale_payment_amount

        # 3. Клиент + Purchase
        client_id = None
        if sale_phone or sale_full_name:
            client_id = await ClientRepository.get_or_create_client(
                phone=sale_phone.strip() if sale_phone else None,
                full_name=sale_full_name.strip() if sale_full_name else None,
                social_network=sale_platform,
                birth_date=sale_birth_date,
                conn=session,
            )

        if client_id:
            items_list = [{"item_text": text, "price": sale_price, "serial": serial}]
            for acc in processed_accessories:
                items_list.append({"item_text": acc["text"], "price": acc["price"]})

            await ClientRepository.add_purchase(
                client_id=client_id,
                items=items_list,
                total_amount=sale_price + accessories_total,
                payment_details={pt: amt for pt, amt in all_payments.items() if amt > 0},
                purchase_type="sale",
                conn=session,
            )

        # 4. Удаление основного товара + DeletedItem
        main_item = await session.get(Item, item_id)
        if main_item:
            deleted = DeletedItem(
                item_id=main_item.id,
                text=old_text,
                serial=old_serial,
                category_id=old_category_id,
                reason="sale_from_admin",
                sale_message_id=sale_message_id,
            )
            session.add(deleted)
            await session.delete(main_item)

        # 5. Запись продажи
        sale = Sale(
            count=1,
            cash=all_payments.get("cash", 0),
            terminal=all_payments.get("terminal", 0),
            qr=all_payments.get("qr", 0),
            transfer=all_payments.get("transfer", 0),
            invoice=all_payments.get("invoice", 0),
            installment=all_payments.get("installment", 0),
            is_accessory=False,
            message_id=sale_message_id,
        )
        session.add(sale)

        # 6. Сохранение платежей
        await create_daily_payments(session, all_payments, sale_message_id)

        if own_session:
            await session.commit()

        # 7. Уведомление
        asyncio.create_task(send_sale_notification(
            item_text=text,
            price=sale_price,
            payment_type=sale_payment_type,
            prepayment=sale_prepayment if sale_prepayment > 0 else None,
            payment_amount=sale_payment_amount if sale_payment_type != "paid" else None,
            platform=sale_platform,
            full_name=sale_full_name,
            phone=sale_phone,
            birth_date=sale_birth_date,
            bonus=sale_bonus,
            change=sale_change,
            change_type=sale_change_type,
            accessories=processed_accessories,
            accessories_total=accessories_total,
        ))

        # 8. Инвалидация кэша
        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        await AssortmentService.invalidate_cache()

        logger.info(f"✅ Продажа успешно завершена: item_id={item_id}, аксессуаров={len(processed_accessories)}")
        return {"success": True}

    except ValueError as e:
        if own_session:
            await session.rollback()
        logger.warning(f"Некорректные данные продажи: {e}")
        return {"error": str(e)}

    except SQLAlchemyError:
        logger.exception("Ошибка БД при продаже из админки")
        if own_session:
            await session.rollback()
        return {"error": "Ошибка базы данных"}

    except Exception as e:
        logger.exception("Неожиданная ошибка в handle_sale_from_form")
        if own_session:
            await session.rollback()
        return {"error": str(e)}

    finally:
        if own_session:
            await session.close()
