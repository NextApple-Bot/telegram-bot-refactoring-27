from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select

from bot.db import get_async_session_factory
from bot.models import Client, Purchase
from web_admin.templates import templates

router = APIRouter()


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
        # === Базовый запрос ===
        query = select(Client).order_by(Client.created_at.desc())

        # === Поиск ===
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Client.full_name.ilike(search_term),
                    Client.phone.ilike(search_term),
                    Client.telegram_username.ilike(search_term),
                )
            )

        # === Пагинация ===
        total_query = select(func.count()).select_from(Client)
        if search:
            total_query = total_query.where(
                or_(
                    Client.full_name.ilike(search_term),
                    Client.phone.ilike(search_term),
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
    """Детальная информация о клиенте и его покупках."""
    async_session = get_async_session_factory()

    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Клиент не найден")

        # Покупки клиента
        purchases_query = (
            select(Purchase)
            .where(Purchase.client_id == client_id)
            .order_by(Purchase.created_at.desc())
        )
        purchases_result = await session.execute(purchases_query)
        purchases = purchases_result.scalars().all()

    return templates.TemplateResponse(
        "client_detail.html",
        {
            "request": request,
            "client": client,
            "purchases": purchases,
        },
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
    """Сохранение изменений клиента."""
    async_session = get_async_session_factory()

    async with async_session() as session:
        async with session.begin():
            client = await session.get(Client, client_id)
            if not client:
                raise HTTPException(status_code=404, detail="Клиент не найден")

            # Обновляем поля
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
    """Удаление клиента (с каскадным удалением покупок)."""
    async_session = get_async_session_factory()

    async with async_session() as session:
        async with session.begin():
            client = await session.get(Client, client_id)
            if not client:
                raise HTTPException(status_code=404, detail="Клиент не найден")

            await session.delete(client)

    return RedirectResponse(url="/admin/clients", status_code=303)
