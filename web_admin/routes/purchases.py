from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Client, Purchase
from web_admin.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def purchases_list(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        purchases = (await session.execute(
            select(Purchase, Client.full_name.label("client_name"))
            .outerjoin(Client, Purchase.client_id == Client.id)
            .order_by(Purchase.created_at.desc())
        )).all()
    return templates.TemplateResponse("purchases.html", {
        "request": request,
        "purchases": purchases,
        "total": len(purchases),
        "page": 1,
        "per_page": 50,
        "total_pages": 1,
        "client_search": "",
        "date_from": "",
        "date_to": "",
        "payment_type": "all",
        "purchase_type": "all",
        "sort_by": "id",
        "sort_order": "desc",
    })


@router.get("/export/csv")
async def export_purchases_csv(request: Request):
    return {"detail": "Export not implemented yet"}
