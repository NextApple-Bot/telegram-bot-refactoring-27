import asyncio
import logging
from datetime import date

from aiogram import Bot
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from bot import config
from bot.db import get_async_session_factory
from bot.models import Booking, DailyPayment, Item
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from web_admin.routes.assortment.notifications import send_booking_notification
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _normalize_birth(value: str | None) -> str | None:
    """YYYY-MM-DD → ДД.ММ.ГГГГ, иначе как есть."""
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


@router.get("/booking/{item_id}", response_class=HTMLResponse)
async def booking_item_form(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")
        if getattr(item, "is_sold", False):
            raise HTTPException(status_code=400, detail="Товар уже продан")

    return templates.TemplateResponse(
        "assortment_booking_item.html",
        {"request": request, "item": item, "error": None, "form_data": None},
    )


@router.post("/booking/{item_id}", response_class=HTMLResponse)
async def booking_item_submit(
    request: Request,
    item_id: int,
    booking_price: float = Form(...),
    booking_prepayment: float | None = Form(None),
    booking_payment_type: str | None = Form(None),
    booking_platform: str | None = Form(None),
    booking_full_name: str | None = Form(None),
    booking_phone: str | None = Form(None),
    booking_birth_date: str | None = Form(None),
    booking_comment: str | None = Form(None),
    booking_bonus: float | None = Form(None),
):
    is_htmx = request.headers.get("hx-request") == "true"

    # Чистые значения клиента
    full_name = _clean(booking_full_name)
    phone = _clean(booking_phone)
    birth_date = _normalize_birth(booking_birth_date)
    platform = _clean(booking_platform)
    payment_type = _clean(booking_payment_type)
    comment = _clean(booking_comment)

    logger.info(
        "Booking submit item=%s name=%r phone=%r birth=%r platform=%r",
        item_id, full_name, phone, birth_date, platform,
    )

    async_session = get_async_session_factory()
    try:
        notif_payload = {}

        async with async_session() as session:
            async with session.begin():
                item = await session.get(Item, item_id, with_for_update=True)
                if not item:
                    raise HTTPException(status_code=404, detail="Товар не найден")
                if getattr(item, "is_sold", False):
                    raise HTTPException(status_code=400, detail="Товар уже продан")

                if not booking_price or booking_price <= 0:
                    return templates.TemplateResponse(
                        "assortment_booking_item.html",
                        {
                            "request": request,
                            "item": item,
                            "error": "Укажите стоимость устройства больше 0",
                            "form_data": {
                                "booking_price": booking_price,
                                "booking_prepayment": booking_prepayment,
                                "booking_payment_type": payment_type,
                                "booking_platform": platform,
                                "booking_full_name": full_name,
                                "booking_phone": phone,
                                "booking_birth_date": birth_date,
                                "booking_comment": comment,
                                "booking_bonus": booking_bonus,
                            },
                        },
                        status_code=400,
                    )

                was_booked = bool(item.is_booked)

                item.is_booked = True
                item.booking_price = booking_price
                item.booking_prepayment = booking_prepayment
                item.booking_payment_type = payment_type
                item.booking_platform = platform
                item.booking_full_name = full_name
                item.booking_phone = phone
                item.booking_birth_date = birth_date
                item.booking_bonus = booking_bonus

                if phone or full_name:
                    await ClientRepository.get_or_create_client(
                        phone=phone,
                        full_name=full_name,
                        social_network=platform,
                        birth_date=birth_date,
                        conn=session,
                    )

                if not was_booked:
                    session.add(
                        Booking(
                            item_id=item.id,
                            total_amount=booking_price,
                        )
                    )

                if booking_prepayment and booking_prepayment > 0 and payment_type:
                    session.add(
                        DailyPayment(
                            type="preorder",
                            payment_type=payment_type,
                            amount=booking_prepayment,
                        )
                    )

                notif_payload = {
                    "item_text": item.text,
                    "serial": item.serial or "",
                    "price": booking_price,
                    "bonus": booking_bonus,
                    "prepayment": booking_prepayment,
                    "platform": platform,
                    "full_name": full_name,
                    "phone": phone,
                    "payment_type": payment_type,
                    "birth_date": birth_date,
                    "comment": comment,
                }

        # После успешного коммита — уведомление
        if notif_payload:
            asyncio.create_task(
                send_booking_notification(
                    bot=Bot(token=config.BOT_TOKEN),
                    is_cancel=False,
                    **notif_payload,
                )
            )

        await AssortmentService.invalidate_cache()
        try:
            await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        except Exception:
            pass

        if is_htmx:
            return Response(status_code=200, headers={"HX-Redirect": "/admin/assortment"})
        return Response(status_code=303, headers={"Location": "/admin/assortment"})

    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Ошибка БД при бронировании item_id=%s", item_id)
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
