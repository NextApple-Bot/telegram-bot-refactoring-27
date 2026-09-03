import asyncio
import logging
import uuid
from datetime import date
from typing import Any, Optional

from aiogram import Bot
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from bot import config
from bot.db import get_async_session_factory
from bot.models import Item
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from bot.services.finalize_sale import finalize_item_sale
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


def _parse_extra_items(form) -> list[dict[str, Any]]:
    ids = form.getlist("extra_item_id")
    prices = form.getlist("extra_item_price")
    result = []
    seen: set[int] = set()
    for i, raw_id in enumerate(ids):
        try:
            iid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if iid <= 0 or iid in seen:
            continue
        seen.add(iid)
        try:
            price = float(prices[i]) if i < len(prices) and prices[i] not in (None, "") else 0.0
        except (ValueError, TypeError):
            price = 0.0
        if price < 0:
            price = 0.0
        result.append({"item_id": iid, "price": price})
    return result


def _parse_discounts(form) -> list[dict[str, Any]]:
    amounts = form.getlist("discount_amount")
    reasons = form.getlist("discount_reason")
    result = []
    for i, raw in enumerate(amounts):
        try:
            amt = float(raw) if raw not in (None, "") else 0.0
        except (ValueError, TypeError):
            amt = 0.0
        if amt <= 0:
            continue
        reason = ""
        if i < len(reasons) and reasons[i]:
            reason = str(reasons[i]).strip()
        result.append({"amount": amt, "reason": reason})
    return result


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
        result.append({"name": name or "Аксессуар", "price": price, "payment_type": pay})
    return result


@router.get("/sale/{item_id}", response_class=HTMLResponse)
async def sale_item_form(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")
        birth = item.booking_birth_date or item.sale_birth_date
        return templates.TemplateResponse(
            "assortment_sale_item.html",
            {"request": request, "item": item, "form_data": None, "birth_date_iso": _to_iso_date(birth), "error": None},
        )


@router.get("/sale-search")
async def sale_search_items(q: str = "", exclude_id: int = 0):
    query = (q or "").strip()
    if len(query) < 2:
        return {"items": []}
    async_session = get_async_session_factory()
    async with async_session() as session:
        stmt = (
            select(Item.id, Item.text, Item.serial, Item.is_booked)
            .where(or_(Item.text.ilike(f"%{query}%"), Item.serial.ilike(f"%{query}%")))
            .order_by(Item.id.desc())
            .limit(15)
        )
        if exclude_id:
            stmt = stmt.where(Item.id != exclude_id)
        rows = (await session.execute(stmt)).all()
        items = [{"id": r.id, "text": r.text or "", "serial": r.serial or "", "is_booked": bool(r.is_booked)} for r in rows]
    return {"items": items}


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
    use_trade_in: str | None = Form(None),
    trade_in_name: str | None = Form(None),
    trade_in_amount: float | None = Form(None),
    trade_in_serial: str | None = Form(None),
    trade_in_battery: str | None = Form(None),
    use_gnc: str | None = Form(None),
    gnc_store: str | None = Form(None),
    gnc_amount: float | None = Form(None),
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
    extra_items = _parse_extra_items(form)
    discounts = _parse_discounts(form)

    full_name = _clean(sale_full_name)
    phone = _clean(sale_phone)
    birth_date = _normalize_birth(sale_birth_date)
    platform = _clean(sale_platform)
    comment = _clean(sale_comment)
    pay_type = _clean(payment_type) or "cash"

    discount = float(sale_discount) if use_discount and sale_discount else None
    if discount and discount > 0 and not any(abs(d["amount"] - discount) < 0.01 for d in discounts):
        discounts = list(discounts) + [{"amount": discount, "reason": ""}]
    if discounts and discount is None:
        discount = sum(d["amount"] for d in discounts)

    bonus = float(sale_bonus) if use_bonus and sale_bonus else None
    change_val = float(change_amount) if use_change and change_amount else None
    change_kind = _clean(change_type) if use_change and change_val else None
    if change_kind not in ("cash", "transfer"):
        change_kind = "cash" if change_val else None

    trade_name = _clean(trade_in_name) if use_trade_in else None
    trade_amount = float(trade_in_amount) if use_trade_in and trade_in_amount else None
    trade_serial = _clean(trade_in_serial) if use_trade_in else None
    trade_battery = _clean(trade_in_battery) if use_trade_in else None
    if trade_amount is not None and trade_amount < 0:
        trade_amount = abs(trade_amount)
    if use_trade_in and trade_amount and not trade_name:
        trade_name = "Trade-in"

    gnc_store_val = _clean(gnc_store) if use_gnc else None
    gnc_amount_val = float(gnc_amount) if use_gnc and gnc_amount else None
    if gnc_amount_val is not None and gnc_amount_val < 0:
        gnc_amount_val = abs(gnc_amount_val)
    if use_gnc and gnc_amount_val and not gnc_store_val:
        gnc_store_val = "ГНЦ"

    payment_amount = float(paid_amount or 0)
    form_data = {
        "sale_price": sale_price, "payment_type": pay_type, "paid_amount": paid_amount,
        "change_amount": change_val, "change_type": change_kind, "sale_prepayment": sale_prepayment,
        "sale_bonus": bonus, "sale_discount": discount, "trade_in_name": trade_name,
        "trade_in_amount": trade_amount, "trade_in_serial": trade_serial, "trade_in_battery": trade_battery,
        "discounts": discounts, "gnc_store": gnc_store_val, "gnc_amount": gnc_amount_val,
        "sale_full_name": full_name, "sale_phone": phone, "sale_birth_date": birth_date,
        "sale_platform": platform, "sale_comment": comment, "create_client": bool(create_client),
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
                    {"request": request, "item": item, "error": "Цена продажи должна быть больше 0",
                     "form_data": form_data, "birth_date_iso": _to_iso_date(birth_date)},
                    status_code=400,
                )
            result = await handle_sale_from_form(
                item_id=item.id, text=item.text, serial=item.serial,
                category_id=item.category_id or 0, old_text=item.text,
                old_serial=item.serial or "", old_category_id=item.category_id or 0,
                sale_price=float(sale_price), sale_prepayment=float(sale_prepayment or 0),
                sale_payment_amount=payment_amount, sale_payment_type=pay_type,
                sale_platform=platform, sale_full_name=full_name, sale_phone=phone,
                sale_birth_date=birth_date, sale_bonus=bonus, sale_discount=discount,
                discounts=discounts, sale_change=change_val, sale_change_type=change_kind,
                accessories=accessories, extra_items=extra_items, sale_comment=comment,
                trade_in_name=trade_name, trade_in_amount=trade_amount,
                trade_in_serial=trade_serial, trade_in_battery=trade_battery,
                gnc_store=gnc_store_val, gnc_amount=gnc_amount_val,
            )
            if result.get("error"):
                return templates.TemplateResponse(
                    "assortment_sale_item.html",
                    {"request": request, "item": item, "error": result["error"],
                     "form_data": form_data, "birth_date_iso": _to_iso_date(birth_date)},
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
    item_id: int, text: str, serial: Optional[str], category_id: int,
    old_text: str, old_serial: str, old_category_id: int, sale_price: float,
    sale_prepayment: float = 0.0, sale_payment_amount: float = 0.0,
    sale_payment_type: str = "cash", sale_platform: Optional[str] = None,
    sale_full_name: Optional[str] = None, sale_phone: Optional[str] = None,
    sale_birth_date: Optional[str] = None, sale_bonus: Optional[float] = None,
    sale_discount: Optional[float] = None, discounts: Optional[list[dict[str, Any]]] = None,
    sale_change: Optional[float] = None, sale_change_type: Optional[str] = None,
    accessories: Optional[list[dict[str, Any]]] = None,
    extra_items: Optional[list[dict[str, Any]]] = None,
    sale_comment: Optional[str] = None, trade_in_name: Optional[str] = None,
    trade_in_amount: Optional[float] = None, trade_in_serial: Optional[str] = None,
    trade_in_battery: Optional[str] = None, gnc_store: Optional[str] = None,
    gnc_amount: Optional[float] = None, conn=None,
) -> dict[str, Any]:
    accessories = accessories or []
    extra_items = extra_items or []
    discounts = discounts or []

    errors = []
    if not sale_price or sale_price <= 0:
        errors.append("Стоимость продажи должна быть больше 0")
    if sale_bonus is not None and sale_bonus < 0:
        errors.append("Бонус не может быть отрицательным")
    if sale_discount is not None and sale_discount < 0:
        errors.append("Скидка не может быть отрицательной")
    if sale_change is not None and sale_change < 0:
        errors.append("Сумма сдачи не может быть отрицательной")
    if trade_in_amount is not None and trade_in_amount < 0:
        errors.append("Сумма trade-in не может быть отрицательной")
    if gnc_amount is not None and gnc_amount < 0:
        errors.append("Сумма ГНЦ не может быть отрицательной")
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
            session=session, item_id=item_id, text=text, serial=serial, category_id=category_id,
            old_text=old_text, old_serial=old_serial, old_category_id=old_category_id,
            sale_price=sale_price, sale_prepayment=sale_prepayment,
            sale_payment_amount=sale_payment_amount, sale_payment_type=sale_payment_type,
            sale_platform=sale_platform, sale_full_name=sale_full_name, sale_phone=sale_phone,
            sale_birth_date=sale_birth_date, sale_bonus=sale_bonus, sale_discount=sale_discount,
            discounts=discounts, sale_change=sale_change, sale_change_type=sale_change_type,
            accessories=accessories, extra_items=extra_items, sale_message_id=sale_message_id,
            sale_comment=sale_comment, trade_in_name=trade_in_name, trade_in_amount=trade_in_amount,
            trade_in_serial=trade_in_serial, trade_in_battery=trade_in_battery,
            gnc_store=gnc_store, gnc_amount=gnc_amount,
        )
        if manage_transaction:
            async with session.begin():
                return await _process_sale_logic(**kwargs)
        return await _process_sale_logic(**kwargs)
    except Exception as e:
        logger.exception("Неожиданная ошибка в handle_sale_from_form")
        return {"error": str(e)}


async def _process_sale_logic(
    session, item_id: int, text: str, serial: Optional[str], category_id: int,
    old_text: str, old_serial: str, old_category_id: int, sale_price: float,
    sale_prepayment: float, sale_payment_amount: float, sale_payment_type: str,
    sale_platform: Optional[str], sale_full_name: Optional[str], sale_phone: Optional[str],
    sale_birth_date: Optional[str], sale_bonus: Optional[float], sale_discount: Optional[float],
    discounts: list[dict[str, Any]], sale_change: Optional[float], sale_change_type: Optional[str],
    accessories: list[dict[str, Any]], extra_items: list[dict[str, Any]], sale_message_id: int,
    sale_comment: Optional[str] = None, trade_in_name: Optional[str] = None,
    trade_in_amount: Optional[float] = None, trade_in_serial: Optional[str] = None,
    trade_in_battery: Optional[str] = None, gnc_store: Optional[str] = None,
    gnc_amount: Optional[float] = None,
) -> dict[str, Any]:
    processed_accessories: list[dict[str, Any]] = []
    accessories_total = 0.0
    other_payments: dict[str, float] = {}
    main_pt = (sale_payment_type or "cash").strip()

    for acc in accessories:
        price = float(acc.get("price", 0) or 0)
        accessories_total += price
        display_text = (acc.get("name") or "").strip() or "Аксессуар"
        pay_type = (acc.get("payment_type") or "cash").strip() or "cash"
        processed_accessories.append({"text": display_text, "price": price, "payment_type": pay_type})
        if price > 0 and pay_type not in ("paid", main_pt):
            other_payments[pay_type] = other_payments.get(pay_type, 0.0) + price

    bonus_val = float(sale_bonus or 0)
    disc_list = list(discounts or [])
    if not disc_list and sale_discount and float(sale_discount) > 0:
        disc_list = [{"amount": float(sale_discount), "reason": ""}]
    discount_val = sum(float(d.get("amount") or 0) for d in disc_list)

    trade_val = float(trade_in_amount or 0)
    if trade_val < 0:
        trade_val = abs(trade_val)
    gnc_val = float(gnc_amount or 0)
    if gnc_val < 0:
        gnc_val = abs(gnc_val)
    prep = float(sale_prepayment or 0)
    other_sum = sum(other_payments.values())

    extra_total = 0.0
    resolved_extras: list[dict[str, Any]] = []
    for ex in extra_items:
        iid = int(ex.get("item_id") or 0)
        if not iid or iid == item_id:
            continue
        ex_item = await session.get(Item, iid)
        if ex_item is None:
            logger.warning("Товар #%s не найден (extra)", iid)
            continue
        price = float(ex.get("price") or 0)
        if price < 0:
            price = 0.0
        extra_total += price
        resolved_extras.append({
            "item_id": ex_item.id, "text": ex_item.text or "", "serial": ex_item.serial,
            "category_id": ex_item.category_id, "price": price,
        })

    # Общая = цена + аксы + доп − скидки − ГНЦ (trade-in НЕ вычитаем)
    goods_total = float(sale_price) + accessories_total + extra_total - discount_val - gnc_val
    if goods_total < 0:
        goods_total = 0.0

    # Trade-in — способ оплаты: уменьшает доплату, не Общую
    primary_needed = max(goods_total - bonus_val - prep - other_sum - trade_val, 0.0)

    primary_amount = primary_needed
    if sale_payment_amount and float(sale_payment_amount) > 0 and main_pt != "paid":
        entered = float(sale_payment_amount)
        if bonus_val > 0 and entered + prep + other_sum + trade_val + 0.01 >= goods_total:
            primary_amount = primary_needed
        elif accessories_total > 0 and abs(entered - float(sale_price)) < 0.01 and other_sum == 0:
            primary_amount = primary_needed
        else:
            primary_amount = entered

    all_payments: dict[str, float] = dict(other_payments)
    if main_pt != "paid" and primary_amount > 0:
        all_payments[main_pt] = all_payments.get(main_pt, 0.0) + primary_amount

    final_amount = goods_total

    client_id = None
    if sale_phone or sale_full_name:
        client_id = await ClientRepository.get_or_create_client(
            phone=sale_phone.strip() if sale_phone else None,
            full_name=sale_full_name.strip() if sale_full_name else None,
            social_network=sale_platform, birth_date=sale_birth_date, conn=session,
        )

    if client_id:
        items_list = [{"item_text": text, "price": sale_price, "serial": serial}]
        for ex in resolved_extras:
            items_list.append({"item_text": ex["text"], "price": ex["price"], "serial": ex.get("serial")})
        for acc in processed_accessories:
            items_list.append({"item_text": acc["text"], "price": acc["price"]})
        if trade_val > 0:
            items_list.append({
                "item_text": f"Trade-in — {(trade_in_name or 'Trade-in').strip()}",
                "price": -trade_val,
            })
        if gnc_val > 0:
            items_list.append({"item_text": f"ГНЦ {(gnc_store or 'ГНЦ').strip()}", "price": -gnc_val})
        payment_details = {pt: amt for pt, amt in all_payments.items() if amt > 0}
        if bonus_val > 0:
            payment_details["uds"] = bonus_val
        await ClientRepository.add_purchase(
            client_id=client_id, items=items_list, total_amount=final_amount,
            payment_details=payment_details, purchase_type="sale", conn=session,
        )

    await finalize_item_sale(
        session, item_id=item_id, item_text=old_text, item_serial=old_serial,
        category_id=old_category_id, message_id=sale_message_id,
        payments={k: v for k, v in all_payments.items() if k != "uds"},
        reason="sale_from_admin", is_accessory=False, delete_item=True, write_payments=True,
    )

    for idx, ex in enumerate(resolved_extras, start=1):
        await finalize_item_sale(
            session, item_id=ex["item_id"], item_text=ex["text"], item_serial=ex.get("serial"),
            category_id=ex.get("category_id"), message_id=int(sale_message_id) + idx,
            payments=None, reason="sale_from_admin", is_accessory=False,
            delete_item=True, write_payments=False,
        )

    bot = Bot(token=config.BOT_TOKEN)
    asyncio.create_task(send_sale_notification(
        bot=bot, item_text=text, item_serial=serial, price=sale_price, payment_type=main_pt,
        prepayment=prep if prep > 0 else None,
        payment_amount=primary_amount if main_pt != "paid" else None,
        payments=all_payments, platform=sale_platform, full_name=sale_full_name,
        phone=sale_phone, birth_date=sale_birth_date, bonus=sale_bonus,
        discount=discount_val if discount_val > 0 else None, discounts=disc_list,
        change=sale_change, change_type=sale_change_type,
        accessories=processed_accessories, accessories_total=accessories_total,
        extra_items=resolved_extras, final_amount=final_amount, comment=sale_comment,
        trade_in_name=trade_in_name, trade_in_amount=trade_val if trade_val > 0 else None,
        trade_in_serial=trade_in_serial, trade_in_battery=trade_in_battery,
        gnc_store=gnc_store, gnc_amount=gnc_val if gnc_val > 0 else None,
    ))

    try:
        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
    except Exception:
        pass
    await AssortmentService.invalidate_cache()
    return {"success": True}
