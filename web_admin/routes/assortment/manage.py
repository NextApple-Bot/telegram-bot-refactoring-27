import asyncio
import logging

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import Category, Item
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from web_admin.templates import templates

from .notifications import send_booking_notification
from .sales import handle_sale_from_form

logger = logging.getLogger(__name__)
router = APIRouter()


def validate_phone(phone: str) -> bool:
    if not phone:
        return True
    import re
    return bool(re.match(r'^\+7\d{10}$', phone))


@router.get("/edit/{item_id}")
async def edit_item_form(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")

        categories_result = await session.execute(
            select(Category.id, Category.name).order_by(Category.sort_order, Category.name)
        )
        categories = [dict(row._mapping) for row in categories_result.all()]

    return templates.TemplateResponse(
        "assortment_edit_item.html",
        {
            "request": request,
            "item": item,
            "categories": categories,
        },
    )


@router.post("/edit/{item_id}")
async def edit_item_submit(
    request: Request,
    item_id: int,
    text: str = Form(...),
    serial: str | None = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
    is_sold: bool = Form(False),
    # Бронирование
    booking_price: float | None = Form(None),
    booking_bonus: float | None = Form(None),
    booking_prepayment: float | None = Form(None),
    booking_platform: str | None = Form(None),
    booking_full_name: str | None = Form(None),
    booking_phone: str | None = Form(None),
    booking_payment_type: str | None = Form(None),
    booking_birth_date: str | None = Form(None),
    # Продажа
    sale_price: float | None = Form(None),
    sale_bonus: float | None = Form(None),
    sale_change: float | None = Form(None),
    sale_change_type: str | None = Form(None),
    sale_prepayment: float | None = Form(None),
    sale_payment_amount: float | None = Form(None),
    sale_payment_type: str | None = Form(None),
    sale_platform: str | None = Form(None),
    sale_full_name: str | None = Form(None),
    sale_phone: str | None = Form(None),
    sale_birth_date: str | None = Form(None),
    # Аксессуары
    accessory_name: list[str] = Form([]),
    accessory_serial: list[str] = Form([]),
    accessory_price: list[float] = Form([]),
    accessory_payment_type: list[str] = Form([]),
):
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона брони")
    if sale_phone and not validate_phone(sale_phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона продажи")

    if is_sold and is_booked:
        raise HTTPException(status_code=400, detail="Нельзя одновременно забронировать и продать товар")

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                old = await session.get(Item, item_id, with_for_update=True)
                if not old:
                    raise HTTPException(status_code=404, detail="Товар не найден")
                if getattr(old, "is_sold", False):
                    raise HTTPException(status_code=400, detail="Товар уже продан")

                old_text = old.text
                old_serial = old.serial or ""
                old_category_id = old.category_id

                # === ПРОДАЖА ===
                if is_sold:
                    accessories = []
                    for name, acc_serial, price, pay_type in zip(
                        accessory_name, accessory_serial, accessory_price, accessory_payment_type, strict=False
                    ):
                        if name and str(name).strip():
                            accessories.append({
                                "name": str(name).strip(),
                                "serial": str(acc_serial).strip().upper() if acc_serial else None,
                                "price": float(price) if price else 0,
                                "payment_type": pay_type if pay_type else None,
                            })

                    result = await handle_sale_from_form(
                        item_id=item_id,
                        text=text,
                        serial=serial,
                        category_id=category_id,
                        old_text=old_text,
                        old_serial=old_serial,
                        old_category_id=old_category_id,
                        sale_price=float(sale_price) if sale_price else 0,
                        sale_prepayment=sale_prepayment or 0,
                        sale_payment_amount=sale_payment_amount or 0,
                        sale_payment_type=sale_payment_type or "cash",
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
                        error_msg = result["error"]
                        return RedirectResponse(
                            url=f"/admin/assortment/edit/{item_id}?error={error_msg}",
                            status_code=303
                        )

                    await AssortmentService.invalidate_cache()
                    return RedirectResponse(url="/admin/assortment", status_code=303)

                # === БРОНИРОВАНИЕ ===
                if is_booked:
                    if not booking_price or booking_price <= 0:
                        raise HTTPException(status_code=400, detail="Укажите стоимость брони")

                    if booking_phone or booking_full_name:
                        await ClientRepository.get_or_create_client(
                            phone=booking_phone,
                            full_name=booking_full_name,
                            social_network=booking_platform,
                            birth_date=booking_birth_date,
                            conn=session,
                        )

                    old.text = text
                    old.serial = serial.strip().upper() if serial else None
                    old.category_id = category_id
                    old.is_booked = True
                    old.is_sold = False
                    old.booking_price = booking_price
                    old.booking_bonus = booking_bonus
                    old.booking_prepayment = booking_prepayment
                    old.booking_platform = booking_platform
                    old.booking_full_name = booking_full_name
                    old.booking_phone = booking_phone
                    old.booking_payment_type = booking_payment_type
                    old.booking_birth_date = booking_birth_date

                    for field in ["sale_price", "sale_bonus", "sale_change", "sale_change_type",
                                  "sale_prepayment", "sale_payment_amount", "sale_payment_type",
                                  "sale_platform", "sale_full_name", "sale_phone", "sale_birth_date"]:
                        setattr(old, field, None)

                    session.add(old)

                    if booking_prepayment and booking_prepayment > 0 and booking_payment_type:
                        from bot.models import DailyPayment
                        payment = DailyPayment(
                            type="preorder",
                            payment_type=booking_payment_type,
                            amount=booking_prepayment,
                        )
                        session.add(payment)

                    asyncio.create_task(send_booking_notification(
                        item_text=text,
                        serial=serial or "",
                        price=booking_price,
                        prepayment=booking_prepayment,
                        platform=booking_platform,
                        full_name=booking_full_name,
                        phone=booking_phone,
                        payment_type=booking_payment_type,
                        birth_date=booking_birth_date,
                        bonus=booking_bonus,
                    ))

                # === ОБЫЧНОЕ РЕДАКТИРОВАНИЕ ===
                else:
                    old.text = text
                    old.serial = serial.strip().upper() if serial else None
                    old.category_id = category_id
                    old.is_booked = False
                    old.is_sold = False

                    for field in [
                        "booking_price", "booking_bonus", "booking_prepayment",
                        "booking_platform", "booking_full_name", "booking_phone",
                        "booking_payment_type", "booking_birth_date",
                        "sale_price", "sale_bonus", "sale_change", "sale_change_type",
                        "sale_prepayment", "sale_payment_amount", "sale_payment_type",
                        "sale_platform", "sale_full_name", "sale_phone", "sale_birth_date"
                    ]:
                        setattr(old, field, None)

                    session.add(old)

            await AssortmentService.invalidate_cache()
            return RedirectResponse(url="/admin/assortment", status_code=303)

        except HTTPException:
            raise
        except SQLAlchemyError as e:
            logger.exception(f"Ошибка БД при редактировании товара {item_id}")
            raise HTTPException(status_code=500, detail="Ошибка базы данных") from e


@router.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        item = await session.get(Item, item_id)
        if item:
            from bot.models import DeletedItem
            deleted = DeletedItem(
                item_id=item.id,
                text=item.text,
                serial=item.serial,
                category_id=item.category_id,
                reason="admin_manual",
            )
            session.add(deleted)
            await session.delete(item)

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)
