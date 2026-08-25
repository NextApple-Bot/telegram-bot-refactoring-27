import asyncio
import logging
import uuid
from datetime import date
from typing import Any, Optional

from aiogram import Bot
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
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


def _to_iso_date(value: str | None) -> str:
    value = _clean(value)
    if not value:
        return ""
    if "-" in value and len(value) == 10:
        return value
    value = value.replace("г.", "").strip()
    if "." in value:
        parts = value.split(".")
        if len(parts) == 3:
            d, m, y = parts
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return ""


def _parse_accessories(form) -> list[dict[str, Any]]:
    names = form.getlist("acc_name")
    prices = form.getlist("acc_price")
    payments = form.getlist("acc_payment")
    result = []
    for i, name in enumerate(names):
        name = (name or "").strip()
        try:
            price = float(prices[i]) if i < len(prices) and prices[i] not in (None, "") else 0.0
        except (ValueError, TypeError):
            price = 0.0
        pay = payments[i] if i < len(payments) else "cash"
        pay = (pay or "cash").strip()
        if not name and price <= 0:
            continue
        result.append({
            "name": name or "Аксессуар",
            "price": price,
            "payment_type": pay,
        })
    return result


@router.get("/sale/{item_id}", response_class=HTMLResponse)
async def sale_item_form(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

    birth_raw = item.booking_birth_date or item.sale_birth_date or ""
    return templates.TemplateResponse(
        "assortment_sale_item.html",
        {
            "request": request,
            "item": item,
            "error": None,
            "form_data": None,
            "birth_date_iso": _to_iso_date(birth_raw),
        },
    )


@router.post("/sale/{item_id}", response_class=HTMLResponse)
async def sale_item_submit(
    request: Request,
    item_id: int,
    sale_price: float = Form(...),
    payment_type: str = Form(...),
    paid_amount: float | None = Form(None),
    change_amount: float | None = Form(None),
    change_type: str | None = Form(None),
    sale_prepayment: float | None = Form(None),
    sale_bonus: float | None = Form(None),
    sale_discount: float | None = Form(None),
    use_bonus: str | None = Form(None),
    use_discount: str | None = Form(None),
    use_change: str | None = Form(None),
    sale_full_name: str | None = Form(None),
    sale_phone: str | None = Form(None),
    sale_birth_date: str | None = Form(None),
    sale_platform: str | None = Form(None),
    sale_comment: str | None = Form(None),
    create_client: str | None = Form(None),
):
    is_htmx = request.headers.get("hx-request") == "true"

    form = await request.form()
    accessories = _parse_accessories(form)

    full_name = _clean(sale_full_name)
    phone = _clean(sale_phone)
    birth_date = _normalize_birth(sale_birth_date)
    platform = _clean(sale_platform)
    comment = _clean(sale_comment)
    pay_type = _clean(payment_type) or "cash"

    bonus = float(sale_bonus) if use_bonus and sale_bonus else None
    discount = float(sale_discount) if use_discount and sale_discount else None
    change_val = float(change_amount) if use_change and change_amount else None
    change_kind = _clean(change_type) if use_change and change_val else None
    if change_kind not in ("cash", "transfer"):
        change_kind = "cash" if change_val else None

    # paid_amount с формы — подсказка; итоговый расчёт в _process_sale_logic
    payment_amount = float(paid_amount or 0)

    form_data = {
        "sale_price": sale_price,
        "payment_type": pay_type,
        "paid_amount": paid_amount,
        "change_amount": change_val,
        "change_type": change_kind,
        "sale_prepayment": sale_prepayment,
        "sale_bonus": bonus,
        "sale_discount": discount,
        "sale_full_name": full_name,
        "sale_phone": phone,
        "sale_birth_date": birth_date,
        "sale_platform": platform,
        "sale_comment": comment,
        "create_client": bool(create_client),
    }

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
                        "form_data": form_data,
                        "birth_date_iso": _to_iso_date(birth_date),
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
                sale_full_name=full_name,
                sale_phone=phone,
                sale_birth_date=birth_date,
                sale_bonus=bonus,
                sale_discount=discount,
                sale_change=change_val,
                sale_change_type=change_kind,
                accessories=accessories,
                sale_comment=comment,
            )

            if result.get("error"):
                return templates.TemplateResponse(
                    "assortment_sale_item.html",
                    {
                        "request": request,
                        "item": item,
                        "error": result["error"],
                        "form_data": form_data,
                        "birth_date_iso": _to_iso_date(birth_date),
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
    sale_discount: Optional[float] = None,
    sale_change: Optional[float] = None,
    sale_change_type: Optional[str] = None,
    accessories: Optional[list[dict[str, Any]]] = None,
    sale_comment: Optional[str] = None,
    conn=None,
) -> dict[str, Any]:
    accessories = accessories or []

    errors = []
    if not sale_price or sale_price <= 0:
        errors.append("Стоимость продажи должна быть больше 0")
    if sale_bonus is not None and sale_bonus < 0:
        errors.append("Бонус не может быть отрицательным")
    if sale_discount is not None and sale_discount < 0:
        errors.append("Скидка не может быть отрицательной")
    if sale_change is not None and sale_change < 0:
        errors.append("Сумма сдачи не может быть отрицательной")

    for i, acc in enumerate(accessories):
        if float(acc.get("price", 0) or 0) < 0:
            errors.append(f"Цена аксессуара №{i+1} не может быть отрицательной")

    if errors:
        return {"error": " | ".join(errors)}

    sale_message_id = generate_sale_message_id()
    async_session = get_async_session_factory()

    if conn is not None:
        session = conn
        manage_transaction = False
    else:
        session = async_session()
        manage_transaction = True

    try:
        kwargs = dict(
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
            sale_discount=sale_discount,
            sale_change=sale_change,
            sale_change_type=sale_change_type,
            accessories=accessories,
            sale_message_id=sale_message_id,
            sale_comment=sale_comment,
        )
        if manage_transaction:
            async with session.begin():
                return await _process_sale_logic(**kwargs)
        return await _process_sale_logic(**kwargs)

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
    sale_discount: Optional[float],
    sale_change: Optional[float],
    sale_change_type: Optional[str],
    accessories: list[dict[str, Any]],
    sale_message_id: int,
    sale_comment: Optional[str] = None,
) -> dict[str, Any]:
    """
    Расчёт оплат:
      товары = цена устройства + сумма аксессуаров − скидка
      UDS   = бонусы (если указаны)
      основной способ (Наличными/…) = товары − UDS − П/О − оплаты аксессуаров другим способом
      Общая = товары (= основной способ + UDS + П/О + прочие)
    """
    processed_accessories: list[dict[str, Any]] = []
    accessories_total = 0.0
    # Аксессуары, оплаченные НЕ основным способом
    other_payments: dict[str, float] = {}

    main_pt = (sale_payment_type or "cash").strip()

    for acc in accessories:
        price = float(acc.get("price", 0) or 0)
        accessories_total += price
        display_text = (acc.get("name") or "").strip() or "Аксессуар"
        pay_type = (acc.get("payment_type") or "cash").strip() or "cash"

        processed_accessories.append({
            "text": display_text,
            "price": price,
            "payment_type": pay_type,
        })

        if price > 0 and pay_type not in ("paid", main_pt):
            other_payments[pay_type] = other_payments.get(pay_type, 0.0) + price

    bonus_val = float(sale_bonus or 0)
    discount_val = float(sale_discount or 0)
    prep = float(sale_prepayment or 0)
    other_sum = sum(other_payments.values())

    # Полная стоимость товаров (то, что уходит в «Общая»)
    goods_total = float(sale_price) + accessories_total - discount_val

    # Сколько должно прийти основным способом оплаты
    primary_needed = max(goods_total - bonus_val - prep - other_sum, 0.0)

    # Если с формы пришла сумма — поправляем, когда забыли вычесть UDS
    primary_amount = primary_needed
    if sale_payment_amount and float(sale_payment_amount) > 0 and main_pt != "paid":
        entered = float(sale_payment_amount)
        # Ввели полную сумму товаров (или цену устройства + аксы) без вычета бонусов
        if bonus_val > 0 and entered + prep + other_sum + 0.01 >= goods_total:
            primary_amount = primary_needed
        # Ввели только цену устройства, аксессуары того же способа — добираем
        elif (
            accessories_total > 0
            and abs(entered - float(sale_price)) < 0.01
            and other_sum == 0
        ):
            primary_amount = primary_needed
        else:
            primary_amount = entered

    all_payments: dict[str, float] = dict(other_payments)
    if main_pt != "paid" and primary_amount > 0:
        all_payments[main_pt] = all_payments.get(main_pt, 0.0) + primary_amount

    # Общая = стоимость товаров (Наличными + UDS + …)
    final_amount = goods_total

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

        payment_details = {pt: amt for pt, amt in all_payments.items() if amt > 0}
        if bonus_val > 0:
            payment_details["uds"] = bonus_val

        await ClientRepository.add_purchase(
            client_id=client_id,
            items=items_list,
            total_amount=final_amount,
            payment_details=payment_details,
            purchase_type="sale",
            conn=session,
        )

    main_item = await session.get(Item, item_id)
    if main_item:
        session.add(DeletedItem(
            item_id=main_item.id,
            text=old_text,
            serial=old_serial,
            category_id=old_category_id,
            reason="sale_from_admin",
            sale_message_id=sale_message_id,
        ))
        await session.delete(main_item)

    session.add(Sale(
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
    ))

    for pay_type, amount in all_payments.items():
        if amount > 0 and pay_type != "uds":
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
        payment_type=main_pt,
        prepayment=prep if prep > 0 else None,
        payment_amount=primary_amount if main_pt != "paid" else None,
        payments=all_payments,
        platform=sale_platform,
        full_name=sale_full_name,
        phone=sale_phone,
        birth_date=sale_birth_date,
        bonus=sale_bonus,
        discount=sale_discount,
        change=sale_change,
        change_type=sale_change_type,
        accessories=processed_accessories,
        accessories_total=accessories_total,
        final_amount=final_amount,
        comment=sale_comment,
    ))

    try:
        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
    except Exception:
        pass
    await AssortmentService.invalidate_cache()

    return {"success": True}
