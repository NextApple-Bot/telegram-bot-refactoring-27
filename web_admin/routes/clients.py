from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Client
from bot.repositories.client import ClientRepository
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def list_clients(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    sort_by: str = Query("id", pattern="^(id|full_name|phone|telegram_username|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    async_session = get_async_session_factory()
    async with async_session() as session:
        offset = (page - 1) * per_page
        base_query = select(Client)
        count_query = select(func.count(Client.id))

        if search:
            base_query = base_query.where(
                (Client.full_name.ilike(f"%{search}%")) |
                (Client.phone.ilike(f"%{search}%")) |
                (Client.telegram_username.ilike(f"%{search}%"))
            )
            count_query = count_query.where(
                (Client.full_name.ilike(f"%{search}%")) |
                (Client.phone.ilike(f"%{search}%")) |
                (Client.telegram_username.ilike(f"%{search}%"))
            )

        if date_from:
            base_query = base_query.where(Client.created_at >= date_from)
            count_query = count_query.where(Client.created_at >= date_from)
        if date_to:
            base_query = base_query.where(Client.created_at <= date_to)
            count_query = count_query.where(Client.created_at <= date_to)

        allowed_sort = {
            "id": Client.id,
            "full_name": Client.full_name,
            "phone": Client.phone,
            "telegram_username": Client.telegram_username,
            "created_at": Client.created_at,
        }
        sort_col = allowed_sort.get(sort_by, Client.id)
        order_dir = sort_col.desc() if sort_order == "desc" else sort_col.asc()

        base_query = base_query.order_by(order_dir).limit(per_page).offset(offset)

        total = (await session.execute(count_query)).scalar()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        clients = (await session.execute(base_query)).scalars().all()

    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "search": search,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_order": sort_order,
    })


@router.get("/{client_id}")
async def client_detail(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            return RedirectResponse(url="/admin/clients")
        purchases = await ClientRepository.get_client_purchases(client_id)

    return templates.TemplateResponse("client_detail.html", {
        "request": request,
        "client": client,
        "purchases": purchases,
    })


@router.get("/{client_id}/edit")
async def edit_client_form(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            return RedirectResponse(url="/admin/clients")

    return templates.TemplateResponse("client_edit.html", {
        "request": request,
        "client": client
    })


@router.post("/{client_id}/edit")
async def edit_client_submit(
    request: Request,
    client_id: int,
    full_name: str = Form(""),
    phone: str = Form(""),
    phones: str = Form(""),
    telegram_username: str = Form(""),
    social_network: str = Form(""),
    referral_source: str = Form(""),
):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        client = await session.get(Client, client_id)
        if client:
            client.full_name = full_name
            client.phone = phone
            client.phones = phones
            client.telegram_username = telegram_username or None
            client.social_network = social_network or None
            client.referral_source = referral_source or None
            client.updated_at = func.now()
            session.add(client)

    return RedirectResponse(url=f"/admin/clients/{client_id}", status_code=303)


@router.post("/delete/{client_id}")
async def delete_client(client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        client = await session.get(Client, client_id)
        if client:
            await session.delete(client)
    return RedirectResponse(url="/admin/clients", status_code=303)
