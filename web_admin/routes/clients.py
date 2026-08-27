import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select, text

from bot.db import get_async_session_factory
from bot.models import Client, Item, Purchase
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_phone(phone: str | None) -> bool:
    if not phone:
        return True
    return bool(re.match(r"^\+7\d{10}$", phone))


def _phone_variants(phone: str | None) -> list[str]:
    """Нормализованные варианты номера для поиска броней."""
    if not phone:
        return []
    digits = re.sub(r"\D", "", phone)
    variants = {phone.strip()}
    if digits:
        variants.add(digits)
        if digits.startswith("8") and len(digits) == 11:
            variants.add("+7" + digits[1:])
            variants.add("7" + digits[1:])
        if digits.startswith("7") and len(digits) == 11:
            variants.add("+" + digits)
            variants.add("8" + digits[1:])
        if len(digits) == 10:
            variants.add("+7" + digits)
            variants.add("8" + digits)
            variants.add("7" + digits)
    return [v for v in variants if v]


def _parse_purchase_items(items_json: str | None) -> list[dict[str, Any]]:
    if not items_json:
        return []
    try:
        data = json.loads(items_json)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except Exception:
        pass
    return []


def _format_payments(details: Any) -> str:
    if not details:
        return "—"
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            return details
    if not isinstance(details, dict):
        return str(details)
    names = {
        "cash": "Наличные",
        "terminal": "Терминал",
        "qr": "QR",
        "transfer": "Перевод",
        "invoice": "Счёт",
        "installment": "Рассрочка",
        "uds": "UDS",
        "paid": "Оплачен",
    }
    parts = []
    for k, v in details.items():
        try:
            amount = float(v or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        label = names.get(k, k)
        parts.append(f"{label}: {int(amount):,}".replace(",", " ") + " ₽")
    return "; ".join(parts) if parts else "—"


@router.get("/", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
):
    async_session = get_async_session_factory()
    offset = (page - 1) * per_page

    async with async_session() as session:
        query = select(Client).order_by(Client.created_at.desc())

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Client.full_name.ilike(search_term),
                    Client.phone.ilike(search_term),
                    Client.phones.ilike(search_term),
                    Client.telegram_username.ilike(search_term),
                )
            )

        total_query = select(func.count()).select_from(Client)
        if search:
            total_query = total_query.where(
                or_(
                    Client.full_name.ilike(search_term),
                    Client.phone.ilike(search_term),
                    Client.phones.ilike(search_term),
                    Client.telegram_username.ilike(search_term),
                )
            )

        total = (await session.execute(total_query)).scalar_one()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        result = await session.execute(query.offset(offset).limit(per_page))
        clients = result.scalars().all()

    return templates.TemplateResponse(
        "clients.html",
        {
            "request": request,
            "clients": clients,
            "page": page,
            "total_pages": total_pages,
            "per_page": per_page,
            "total": total,
            "search": search,
        },
    )


@router.get("/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        purchases_raw = (
            await session.execute(
                select(Purchase)
                .where(Purchase.client_id == client_id)
                .order_by(Purchase.created_at.desc())
            )
        ).scalars().all()

        purchases = []
        total_spent = 0.0
        for p in purchases_raw:
            amount = float(p.total_amount or 0)
            total_spent += amount
            purchases.append(
                {
                    "id": p.id,
                    "created_at": p.created_at,
                    "total_amount": amount,
                    "purchase_type": p.purchase_type or "sale",
                    "items": _parse_purchase_items(p.items_json),
                    "payments": _format_payments(p.payment_details),
                    "payment_details": p.payment_details,
                }
            )

        # Телефоны
        phones_list: list[str] = []
        if client.phone:
            phones_list.append(client.phone.strip())
        if client.phones:
            for part in re.split(r"[,;\n]+", client.phones):
                part = part.strip()
                if part and part not in phones_list:
                    phones_list.append(part)

        # Активные брони: по телефону или ФИО
        booking_filters = [Item.is_booked.is_(True)]
        phone_ors = []
        for ph in phones_list:
            for v in _phone_variants(ph):
                phone_ors.append(Item.booking_phone.ilike(f"%{v}%"))
        name_ors = []
        if client.full_name and len(client.full_name.strip()) >= 3:
            name_ors.append(Item.booking_full_name.ilike(f"%{client.full_name.strip()}%"))

        bookings = []
        if phone_ors or name_ors:
            match = or_(*(phone_ors + name_ors))
            booking_q = (
                select(Item)
                .where(Item.is_booked.is_(True), match)
                .order_by(Item.id.desc())
                .limit(50)
            )
            booking_rows = (await session.execute(booking_q)).scalars().all()
            for it in booking_rows:
                bookings.append(
                    {
                        "id": it.id,
                        "text": it.text,
                        "serial": it.serial,
                        "price": float(it.booking_price or 0) or None,
                        "prepayment": float(it.booking_prepayment or 0) or None,
                        "platform": it.booking_platform,
                        "full_name": it.booking_full_name,
                        "phone": it.booking_phone,
                        "payment_type": it.booking_payment_type,
                    }
                )

    return templates.TemplateResponse(
        "client_detail.html",
        {
            "request": request,
            "client": client,
            "purchases": purchases,
            "bookings": bookings,
            "phones_list": phones_list,
            "total_spent": total_spent,
            "purchases_count": len(purchases),
            "bookings_count": len(bookings),
        },
    )


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def client_edit_form(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

    return templates.TemplateResponse(
        "client_edit.html",
        {"request": request, "client": client},
    )


@router.post("/{client_id}/edit")
async def client_edit_submit(
    request: Request,
    client_id: int,
    full_name: str = Form(None),
    phone: str = Form(None),
    phones: str = Form(None),
    telegram_username: str = Form(None),
    social_network: str = Form(None),
    referral_source: str = Form(None),
    birth_date: str = Form(None),
):
    if phone and not _validate_phone(phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона")

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        client.full_name = full_name or None
        client.phone = phone or None
        client.phones = phones or None
        client.telegram_username = telegram_username or None
        client.social_network = social_network or None
        client.referral_source = referral_source or None
        client.birth_date = birth_date or None

        session.add(client)

    return RedirectResponse(url=f"/admin/clients/{client_id}", status_code=303)


@router.post("/{client_id}/delete")
async def client_delete(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        await session.execute(
            text("DELETE FROM purchases WHERE client_id = :client_id"),
            {"client_id": client_id},
        )
        await session.delete(client)

    return RedirectResponse(url="/admin/clients", status_code=303)
