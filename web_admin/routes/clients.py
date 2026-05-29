from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Client, Purchase
from web_admin.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def clients_list(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        clients = (await session.execute(select(Client).order_by(Client.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "total": len(clients),
        "page": 1,
        "per_page": 50,
        "total_pages": 1,
        "search": "",
        "date_from": "",
        "date_to": "",
        "sort_by": "id",
        "sort_order": "desc",
    })


@router.get("/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        client = (await session.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
        if not client:
            return RedirectResponse("/admin/clients")
        purchases = (await session.execute(select(Purchase).where(Purchase.client_id == client_id).order_by(Purchase.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("client_detail.html", {"request": request, "client": client, "purchases": purchases})


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def client_edit(request: Request, client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        client = (await session.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
        if not client:
            return RedirectResponse("/admin/clients")
    return templates.TemplateResponse("client_edit.html", {"request": request, "client": client})


@router.post("/{client_id}/edit")
async def client_edit_post(
    client_id: int,
    full_name: str = Form(...),
    phone: str = Form(...),
    telegram_username: str = Form(""),
    social_network: str = Form(""),
    referral_source: str = Form(""),
):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        client = (await session.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
        if client:
            client.full_name = full_name
            client.phone = phone
            client.telegram_username = telegram_username or None
            client.social_network = social_network or None
            client.referral_source = referral_source or None
    return RedirectResponse(f"/admin/clients/{client_id}", status_code=303)


@router.post("/{client_id}/delete")
async def client_delete(client_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        client = (await session.execute(select(Client).where(Client.id == client_id))).scalar_one_or_none()
        if client:
            await session.delete(client)
    return RedirectResponse("/admin/clients", status_code=303)
