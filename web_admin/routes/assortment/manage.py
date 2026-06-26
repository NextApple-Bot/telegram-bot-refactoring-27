import asyncio
import logging
import re
from fastapi import APIRouter, Form, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from starlette.responses import Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from bot import config
from bot.db import get_async_session_factory
from bot.models import Category, DailyPayment, DeletedItem, Item
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from web_admin.templates import templates
from web_admin.dependencies import get_async_session
from .notifications import send_booking_notification
from .sales import handle_sale_from_form

logger = logging.getLogger(__name__)
router = APIRouter()


def validate_phone(phone: str) -> bool:
    if not phone:
        return True
    return bool(re.match(r'^\+7\d{10}$', phone))


def validate_telegram_username(username: str | None) -> bool:
    if not username:
        return True
    username = username.strip()
    if username.startswith("@"):
        username = username[1:]
    return bool(re.match(r'^[a-zA-Z0-9_]{5,32}$', username))


def validate_comment(comment: str | None) -> bool:
    if not comment:
        return True
    return len(comment.strip()) <= 200


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
        categories = [{"id": row.id, "name": row.name} for row in categories_result.all()]

    return templates.TemplateResponse(
        "assortment_edit_item.html",
        {
            "request": request,
            "item": item,
            "categories": categories,
            "selected_category_id": item.category_id,
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
    booking_price: float | None = Form(None),
    booking_bonus: float | None = Form(None),
    booking_prepayment: float | None = Form(None),
    booking_platform: str | None = Form(None),
    booking_full_name: str | None = Form(None),
    booking_phone: str | None = Form(None),
    booking_payment_type: str | None = Form(None),
    booking_birth_date: str | None = Form(None),
    booking_telegram_username: str | None = Form(None),
    booking_comment: str | None = Form(None),
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
    accessory_name: list[str] = Form([]),
    accessory_serial: list[str] = Form([]),
    accessory_price: list[float] = Form([]),
    accessory_payment_type: list[str] = Form([]),
):
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона брони")
    if sale_phone and not validate_phone(sale_phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона продажи")

    is_htmx = request.headers.get("hx-request") == "true"

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
                        raise HTTPException(status_code=400, detail=result["error"])

                    await AssortmentService.invalidate_cache()

                    if is_htmx:
                        return Response(status_code=200, headers={"HX-Trigger": "modal-close"})
                    return RedirectResponse(url="/admin/assortment", status_code=303)

                # Обычное редактирование
                booking_fields = [
                    "booking_price", "booking_bonus", "booking_prepayment", "booking_platform",
                    "booking_full_name", "booking_phone", "booking_payment_type", "booking_birth_date",
                    "booking_telegram_username", "booking_comment"
                ]
                sale_fields = [
                    "sale_price", "sale_bonus", "sale_change", "sale_change_type",
                    "sale_prepayment", "sale_payment_amount", "sale_payment_type", "sale_platform",
                    "sale_full_name", "sale_phone", "sale_birth_date"
                ]

                for field in booking_fields + sale_fields:
                    setattr(old, field, None)

                old.text = text
                old.serial = serial.strip().upper() if serial else None
                old.category_id = category_id
                old.is_booked = is_booked
                old.is_sold = False

                if is_booked:
                    if not booking_price or booking_price <= 0:
                        raise HTTPException(status_code=400, detail="Укажите стоимость брони")

                    if booking_phone or booking_full_name:
                        await ClientRepository.get_or_create_client(
                            phone=booking_phone, full_name=booking_full_name,
                            social_network=booking_platform, birth_date=booking_birth_date, conn=session
                        )

                    old.booking_price = booking_price
                    old.booking_bonus = booking_bonus
                    old.booking_prepayment = booking_prepayment
                    old.booking_platform = booking_platform
                    old.booking_full_name = booking_full_name
                    old.booking_phone = booking_phone
                    old.booking_payment_type = booking_payment_type
                    old.booking_birth_date = booking_birth_date
                    old.booking_telegram_username = booking_telegram_username
                    old.booking_comment = booking_comment

                    if booking_prepayment and booking_prepayment > 0 and booking_payment_type:
                        payment = DailyPayment(type='preorder', payment_type=booking_payment_type, amount=booking_prepayment)
                        session.add(payment)

                    asyncio.create_task(send_booking_notification(
                        bot=Bot(token=config.BOT_TOKEN),
                        item_text=text, serial=serial.strip().upper() if serial else "",
                        price=booking_price, bonus=booking_bonus, prepayment=booking_prepayment,
                        platform=booking_platform, full_name=booking_full_name, phone=booking_phone,
                        payment_type=booking_payment_type, birth_date=booking_birth_date, is_cancel=False
                    ))
                else:
                    if old.is_booked:
                        asyncio.create_task(send_booking_notification(
                            bot=Bot(token=config.BOT_TOKEN),
                            item_text=old_text, serial=old_serial, is_cancel=True
                        ))

        except HTTPException:
            raise
        except SQLAlchemyError as e:
            logger.exception(f"Ошибка БД при редактировании товара {item_id}")
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from e

    await AssortmentService.invalidate_cache()

    if is_htmx:
        return Response(status_code=200, headers={"HX-Trigger": "modal-close"})
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.delete("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        item = await session.get(Item, item_id)
        if item:
            deleted = DeletedItem(
                item_id=item.id,
                text=item.text,
                serial=item.serial,
                category_id=item.category_id,
                reason='admin_manual'
            )
            session.add(deleted)
            await session.delete(item)

    await AssortmentService.invalidate_cache()

    if request.headers.get("hx-request"):
        return Response(status_code=200, headers={"HX-Refresh": "true"})

    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add")
async def add_item(
    request: Request,
    text: str = Form(...),
    serial: str | None = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
    booking_price: float | None = Form(None),
    booking_bonus: float | None = Form(None),
    booking_prepayment: float | None = Form(None),
    booking_platform: str | None = Form(None),
    booking_full_name: str | None = Form(None),
    booking_phone: str | None = Form(None),
    booking_payment_type: str | None = Form(None),
):
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Неверный формат телефона брони")

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        new_item = Item(
            text=text,
            serial=serial.strip().upper() if serial else None,
            category_id=category_id,
            is_booked=is_booked,
            booking_price=booking_price,
            booking_bonus=booking_bonus,
            booking_prepayment=booking_prepayment,
            booking_platform=booking_platform,
            booking_full_name=booking_full_name,
            booking_phone=booking_phone,
            booking_payment_type=booking_payment_type
        )
        session.add(new_item)

        if is_booked and booking_prepayment and booking_prepayment > 0 and booking_payment_type:
            payment = DailyPayment(
                type='preorder',
                payment_type=booking_payment_type,
                amount=booking_prepayment
            )
            session.add(payment)

            asyncio.create_task(send_booking_notification(
                bot=Bot(token=config.BOT_TOKEN),
                item_text=text,
                serial=serial.strip().upper() if serial else "",
                price=booking_price,
                bonus=booking_bonus,
                prepayment=booking_prepayment,
                platform=booking_platform,
                full_name=booking_full_name,
                phone=booking_phone,
                payment_type=booking_payment_type,
                is_cancel=False
            ))

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add_category")
async def add_category(request: Request, name: str = Form(...)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название категории не может быть пустым")

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        existing = await session.execute(
            select(Category.id).where(func.lower(Category.name) == func.lower(name))
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Категория с таким названием уже существует")

        max_order = await session.execute(select(func.coalesce(func.max(Category.sort_order), -1)))
        new_category = Category(name=name, sort_order=max_order.scalar() + 1)
        session.add(new_category)

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.get("/categories/manage")
async def manage_categories(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        result = await session.execute(select(Category).order_by(Category.sort_order))
        categories = result.scalars().all()

    return templates.TemplateResponse(
        "partials/manage_categories.html",
        {"request": request, "categories": categories}
    )


@router.post("/categories/reorder")
async def reorder_categories(request: Request):
    data = await request.json()
    category_ids = data.get("order", [])

    async_session = get_async_session_factory()
    async with async_session() as session:
        for index, cat_id in enumerate(category_ids):
            await session.execute(
                update(Category).where(Category.id == cat_id).values(sort_order=index)
            )
        await session.commit()

    await AssortmentService.invalidate_cache()
    return {"status": "success"}
