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


@router.get("/booking/{item_id}", response_class=HTMLResponse)
async def booking_item_form(request: Request, item_id: int):
    """Форма бронирования товара (модалка из ассортимента)."""
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
    """Сохранение брони из админки."""
    is_htmx = request.headers.get("hx-request") == "true"

    # Нормализация даты рождения из <input type="date"> (YYYY-MM-DD) → ДД.ММ.ГГГГ
    if booking_birth_date and "-" in booking_birth_date and len(booking_birth_date) == 10:
        try:
            y, m, d = booking_birth_date.split("-")
            booking_birth_date = f"{d}.{m}.{y}"
        except ValueError:
            pass

    async_session = get_async_session_factory()
    try:
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
                                "booking_payment_type": booking_payment_type,
                                "booking_platform": booking_platform,
                                "booking_full_name": booking_full_name,
                                "booking_phone": booking_phone,
                                "booking_birth_date": booking_birth_date,
                                "booking_comment": booking_comment,
                                "booking_bonus": booking_bonus,
                            },
                        },
                        status_code=400,
                    )

                was_booked = bool(item.is_booked)

                item.is_booked = True
                item.booking_price = booking_price
                item.booking_prepayment = booking_prepayment
                item.booking_payment_type = booking_payment_type
                item.booking_platform = booking_platform
                item.booking_full_name = booking_full_name
                item.booking_phone = booking_phone
                item.booking_birth_date = booking_birth_date
                item.booking_comment = booking_comment
                item.booking_bonus = booking_bonus

                if booking_phone or booking_full_name:
                    await ClientRepository.get_or_create_client(
                        phone=booking_phone.strip() if booking_phone else None,
                        full_name=booking_full_name.strip() if booking_full_name else None,
                        social_network=booking_platform,
                        birth_date=booking_birth_date,
                        conn=session,
                    )

                # Запись в таблицу bookings (для дашборда)
                if not was_booked:
                    session.add(
                        Booking(
                            item_id=item.id,
                            total_amount=booking_price,
                        )
                    )

                if booking_prepayment and booking_prepayment > 0 and booking_payment_type:
                    session.add(
                        DailyPayment(
                            type="preorder",
                            payment_type=booking_payment_type,
                            amount=booking_prepayment,
                        )
                    )

                asyncio.create_task(
                    send_booking_notification(
                        bot=Bot(token=config.BOT_TOKEN),
                        item_text=item.text,
                        serial=item.serial or "",
                        price=booking_price,
                        bonus=booking_bonus,
                        prepayment=booking_prepayment,
                        platform=booking_platform,
                        full_name=booking_full_name,
                        phone=booking_phone,
                        payment_type=booking_payment_type,
                        birth_date=booking_birth_date,
                        is_cancel=False,
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
