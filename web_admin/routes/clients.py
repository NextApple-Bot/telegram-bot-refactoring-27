import logging

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select

from bot.db import get_async_session_factory
from bot.models import Client, Purchase
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_phone(phone: str | None) -> bool:
    """Простая валидация телефона."""
    if not phone:
        return True
    import re
    return bool(re.match(r'^\+7\d{10}$', phone))


@router.get("/", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
):
    """
    Список клиентов с поиском и пагинацией.
    """
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
                    Client.phones.ilike(search_term),           # ← Улучшено: поиск по доп. телефонам
                    Client.telegram_username.ilike(search_term),
                )
            )

        # Подсчёт общего количества
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
    """Детальная карточка клиента + история покупок."""
    async_session = get_async_session_factory()

    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        purchases = (
            await session.execute(
                select(Purchase)
                .where(Purchase.client_id == client_id)
                .order_by(Purchase.created_at.desc())
            )
        ).scalars().all()

    return templates.TemplateResponse(
        "client_detail.html",
        {"request": request, "client": client, "purchases": purchases},
    )


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def client_edit_form(request: Request, client_id: int):
    """Форма редактирования клиента."""
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
    """Сохранение изменений клиента с базовой валидацией."""
    if phone and not _validate_phone(phone):
        raise HTTPException(status_code=400, detail="Неверный формат основного телефона")

    async_session = get_async_session_factory()

    try:
        async with async_session() as session:
            async with session.begin():
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

    except Exception as e:
        logger.exception(f"Ошибка при редактировании клиента {client_id}")
        raise HTTPException(status_code=500, detail="Не удалось сохранить изменения") from e


@router.post("/{client_id}/delete")
async def client_delete(request: Request, client_id: int):
    """
    Удаление клиента с явным удалением связанных покупок.
    Это безопаснее, чем полагаться только на каскад в модели.
    """
    async_session = get_async_session_factory()

    try:
        async with async_session() as session:
            async with session.begin():
                client = await session.get(Client, client_id)
                if not client:
                    raise HTTPException(status_code=404, detail="Клиент не найден")

                # Явно удаляем все покупки клиента (защита данных)
                await session.execute(
                    Purchase.__table__.delete().where(Purchase.client_id == client_id)
                )

                # Удаляем самого клиента
                await session.delete(client)

                logger.info(f"Клиент #{client_id} и его покупки удалены")

        return RedirectResponse(url="/admin/clients", status_code=303)

    except Exception as e:
        logger.exception(f"Ошибка при удалении клиента {client_id}")
        raise HTTPException(status_code=500, detail="Не удалось удалить клиента") from e
