import asyncio
import logging
import uuid
from datetime import date
from typing import Any, Optional

from aiogram import Bot
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot import config
from bot.db import get_async_session_factory
from bot.models import DailyPayment, DeletedItem, Item, Sale
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from web_admin.routes.assortment.notifications import send_sale_notification
from web_admin.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def generate_sale_message_id() -> int:
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF


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
    accessories = accessories or []

    # ====================== ВАЛИДАЦИЯ ======================
    errors = []
    if not sale_price or sale_price <= 0:
        errors.append("Стоимость продажи должна быть больше 0")
    if sale_bonus is not None and sale_bonus < 0:
        errors.append("Бонус не может быть отрицательным")
    if sale_bonus and sale_bonus > sale_price:
        errors.append("Бонус не может быть больше стоимости товара")
    if sale_change is not None and sale_change < 0:
        errors.append("Сумма сдачи не может быть отрицательной")
    for i, acc in enumerate(accessories):
        if float(acc.get("price", 0) or 0) < 0:
            errors.append(f"Цена аксессуара №{i+1} не может быть отрицательной")
    if errors:
        return {"error": " | ".join(errors)}
    # =====================================================

    sale_message_id: int = generate_sale_message_id()
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

        # === 1. Обработка аксессуаров ===
        processed_accessories = []
        accessories_payments: dict[str, float] = {}
        accessories_total = 0.0

        for acc in accessories:
            price = float(acc.get("price", 0) or 0)
            accessories_total += price
            display_text = acc.get("name", "").strip() or "Аксессуар"

            serial_acc = acc.get("serial")
            if serial_acc:
                normalized = serial_acc.strip().upper()
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

            processed_accessories.append({
                "text": display_text,
                "price": price,
                "payment_type": pay_type,
            })

        # === 2. Расчёт итоговой суммы ===
        final_amount = sale_price + accessories_total - (sale_bonus or 0)

        # === 3. Сбор платежей ===
        all_payments: dict[str, float] = dict(accessories_payments)
        if sale_payment_type != "paid" and sale_payment_amount > 0:
            all_payments[sale_payment_type] = all_payments.get(sale_payment_type, 0) + sale_payment_amount

        # === 4. Создание клиента ===
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
                total_amount=final_amount,
                payment_details={pt: amt for pt, amt in all_payments.items() if amt > 0},
                purchase_type="sale",
                conn=session,
            )

        # === 5. Удаление товара ===
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

        # === 6. Запись продажи ===
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

        # === 7. Сохранение платежей ===
        for pay_type, amount in all_payments.items():
            if amount > 0:
                session.add(DailyPayment(
                    type="sale",
                    payment_type=pay_type,
                    amount=amount,
                    sale_message_id=sale_message_id,
                ))

        if own_session:
            await session.commit()

        # === 8. Уведомление о продаже ===
        bot = Bot(token=config.BOT_TOKEN)
        asyncio.create_task(send_sale_notification(
            bot=bot,
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
            final_amount=final_amount,
        ))

        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        await AssortmentService.invalidate_cache()

        return {"success": True}

    except ValueError as e:
        if own_session:
            await session.rollback()
        logger.warning(f"Ошибка валидации: {e}")
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


# ====================== РОУТЕРЫ ======================

@router.get("/sale/{item_id}", response_class=HTMLResponse)
async def sale_form(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")
        if getattr(item, "is_sold", False):
            raise HTTPException(status_code=400, detail="Товар уже продан")

    return templates.TemplateResponse(
        "assortment_edit_item.html",
        {"request": request, "item": item, "sale_mode": True}
    )


@router.post("/sale/{item_id}")
async def process_sale(
    request: Request,
    item_id: int,
    sale_price: float = Form(...),
    sale_prepayment: float = Form(0.0),
    sale_payment_amount: float = Form(0.0),
    sale_payment_type: str = Form(...),
    sale_platform: str = Form(""),
    sale_full_name: str = Form(""),
    sale_phone: str = Form(""),
    sale_birth_date: str = Form(""),
    sale_bonus: float = Form(0.0),
    sale_change: float = Form(0.0),
    sale_change_type: str = Form(""),
    accessory_name: list[str] = Form([]),
    accessory_serial: list[str] = Form([]),
    accessory_price: list[float] = Form([]),
    accessory_payment_type: list[str] = Form([]),
):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        accessories = []
        for name, serial, price, pay_type in zip(
            accessory_name, accessory_serial, accessory_price, accessory_payment_type, strict=False
        ):
            if name and str(name).strip():
                accessories.append({
                    "name": str(name).strip(),
                    "serial": str(serial).strip().upper() if serial else None,
                    "price": float(price) if price else 0,
                    "payment_type": pay_type if pay_type else None,
                })

        result = await handle_sale_from_form(
            item_id=item_id,
            text=item.text,
            serial=item.serial,
            category_id=item.category_id,
            old_text=item.text,
            old_serial=item.serial or "",
            old_category_id=item.category_id,
            sale_price=sale_price,
            sale_prepayment=sale_prepayment,
            sale_payment_amount=sale_payment_amount,
            sale_payment_type=sale_payment_type,
            sale_platform=sale_platform,
            sale_full_name=sale_full_name,
            sale_phone=sale_phone,
            sale_birth_date=sale_birth_date,
            sale_bonus=sale_bonus,
            sale_change=sale_change,
            sale_change_type=sale_change_type,
            accessories=accessories,
            conn=session,
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

    return RedirectResponse(url="/admin/assortment", status_code=303)
