import asyncio
import logging
import uuid
from datetime import date
from typing import Any, Optional

from aiogram import Bot
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
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


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _normalize_birth(value: str | None) -> str | None:
    value = _clean(value)
    if not value:
        return None
    if "-" in value and len(value) == 10:
        try:
            y, m, d = value.split("-")
            return f"{d}.{m}.{y}"
        except ValueError:
            return value
    return value


@router.get("/sale/{item_id}", response_class=HTMLResponse)
async def sale_item_form(request: Request, item_id: int):
    """Форма продажи товара."""
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

    return templates.TemplateResponse(
        "assortment_sale_item.html",
        {"request": request, "item": item, "error": None, "form_data": None},
    )


@router.post("/sale/{item_id}", response_class=HTMLResponse)
async def sale_item_submit(
    request: Request,
    item_id: int,
    sale_price: float = Form(...),
    payment_type: str = Form(...),
    paid_amount: float | None = Form(None),
    change_amount: float | None = Form(None),
    sale_prepayment: float | None = Form(None),
    sale_bonus: float | None = Form(None),
    sale_full_name: str | None = Form(None),
    sale_phone: str | None = Form(None),
    sale_birth_date: str | None = Form(None),
    sale_platform: str | None = Form(None),
    sale_comment: str | None = Form(None),
    create_client: str | None = Form(None),
):
    """Сохранение продажи из админки."""
    is_htmx = request.headers.get("hx-request") == "true"

    full_name = _clean(sale_full_name)
    phone = _clean(sale_phone)
    birth_date = _normalize_birth(sale_birth_date)
    platform = _clean(sale_platform)
    pay_type = _clean(payment_type) or "cash"

    payment_amount = float(paid_amount or 0)
    if payment_amount <= 0 and pay_type != "paid":
        # если сумму не указали — берём цену минус предоплата минус бонус
        prep = float(sale_prepayment or 0)
        bonus = float(sale_bonus or 0)
        payment_amount = max(float(sale_price) - prep - bonus, 0)

    async_session = get_async_session_factory()
    try:
        async with async_session() as session:
            item = await session.get(Item, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Товар не найден")

            if not sale_price or sale_price <= 0:
                return templates.TemplateResponse(
                    "assortment_sale_item.html",
                    {
                        "request": request,
                        "item": item,
                        "error": "Цена продажи должна быть больше 0",
                        "form_data": {
                            "sale_price": sale_price,
                            "payment_type": pay_type,
                            "paid_amount": paid_amount,
                            "change_amount": change_amount,
                            "sale_prepayment": sale_prepayment,
                            "sale_bonus": sale_bonus,
                            "sale_full_name": full_name,
                            "sale_phone": phone,
                            "sale_birth_date": birth_date,
                            "sale_platform": platform,
                            "sale_comment": sale_comment,
                            "create_client": bool(create_client),
                        },
                    },
                    status_code=400,
                )

            result = await handle_sale_from_form(
                item_id=item.id,
                text=item.text,
                serial=item.serial,
                category_id=item.category_id or 0,
                old_text=item.text,
                old_serial=item.serial or "",
                old_category_id=item.category_id or 0,
                sale_price=float(sale_price),
                sale_prepayment=float(sale_prepayment or 0),
                sale_payment_amount=payment_amount,
                sale_payment_type=pay_type,
                sale_platform=platform,
                sale_full_name=full_name if create_client else full_name,
                sale_phone=phone if create_client else phone,
                sale_birth_date=birth_date,
                sale_bonus=float(sale_bonus) if sale_bonus else None,
                sale_change=float(change_amount) if change_amount else None,
                sale_change_type=pay_type if change_amount else None,
            )

            if result.get("error"):
                return templates.TemplateResponse(
                    "assortment_sale_item.html",
                    {
                        "request": request,
                        "item": item,
                        "error": result["error"],
                        "form_data": {
                            "sale_price": sale_price,
                            "payment_type": pay_type,
                            "paid_amount": paid_amount,
                            "change_amount": change_amount,
                            "sale_prepayment": sale_prepayment,
                            "sale_bonus": sale_bonus,
                            "sale_full_name": full_name,
                            "sale_phone": phone,
                            "sale_birth_date": birth_date,
                            "sale_platform": platform,
                            "sale_comment": sale_comment,
                            "create_client": bool(create_client),
                        },
                    },
                    status_code=400,
                )

        if is_htmx:
            return Response(status_code=200, headers={"HX-Redirect": "/admin/assortment"})
        return Response(status_code=303, headers={"Location": "/admin/assortment"})

    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Ошибка БД при продаже item_id=%s", item_id)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


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

    sale_message_id: int = generate_sale_message_id()
    async_session = get_async_session_factory()

    if conn is not None:
        session = conn
        manage_transaction = False
    else:
        session = async_session()
        manage_transaction = True

    try:
        if manage_transaction:
            async with session.begin():
                result = await _process_sale_logic(
                    session=session,
                    item_id=item_id,
                    text=text,
                    serial=serial,
                    category_id=category_id,
                    old_text=old_text,
                    old_serial=old_serial,
                    old_category_id=old_category_id,
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
                    sale_message_id=sale_message_id,
                )
        else:
            result = await _process_sale_logic(
                session=session,
                item_id=item_id,
                text=text,
                serial=serial,
                category_id=category_id,
                old_text=old_text,
                old_serial=old_serial,
                old_category_id=old_category_id,
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
                sale_message_id=sale_message_id,
            )

        return result

    except Exception as e:
        logger.exception("Неожиданная ошибка в handle_sale_from_form")
        return {"error": str(e)}


async def _process_sale_logic(
    session,
    item_id: int,
    text: str,
    serial: Optional[str],
    category_id: int,
    old_text: str,
    old_serial: str,
    old_category_id: int,
    sale_price: float,
    sale_prepayment: float,
    sale_payment_amount: float,
    sale_payment_type: str,
    sale_platform: Optional[str],
    sale_full_name: Optional[str],
    sale_phone: Optional[str],
    sale_birth_date: Optional[str],
    sale_bonus: Optional[float],
    sale_change: Optional[float],
    sale_change_type: Optional[str],
    accessories: list[dict[str, Any]],
    sale_message_id: int,
) -> dict[str, Any]:
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

    final_amount = sale_price + accessories_total - (sale_bonus or 0)

    all_payments: dict[str, float] = dict(accessories_payments)
    if sale_payment_type != "paid" and sale_payment_amount > 0:
        all_payments[sale_payment_type] = all_payments.get(sale_payment_type, 0) + sale_payment_amount

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

    sale = Sale(
        item_id=item_id,
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

    for pay_type, amount in all_payments.items():
        if amount > 0:
            session.add(DailyPayment(
                type="sale",
                payment_type=pay_type,
                amount=amount,
                sale_message_id=sale_message_id,
            ))

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

    try:
        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
    except Exception:
        pass
    await AssortmentService.invalidate_cache()

    return {"success": True}
