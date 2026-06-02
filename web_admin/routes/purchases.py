from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Client, Purchase
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def list_purchases(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    client_search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    payment_type: str = Query("all"),
    purchase_type: str = Query("all"),
):
    async_session = get_async_session_factory()
    async with async_session() as session:
        offset = (page - 1) * per_page

        base_query = (
            select(Purchase, Client.full_name.label("client_name"))
            .outerjoin(Client, Purchase.client_id == Client.id)
        )
        count_query = select(func.count(Purchase.id)).outerjoin(Client, Purchase.client_id == Client.id)

        if client_search:
            base_query = base_query.where(
                (Client.full_name.ilike(f"%{client_search}%")) | (Client.phone.ilike(f"%{client_search}%"))
            )
            count_query = count_query.where(
                (Client.full_name.ilike(f"%{client_search}%")) | (Client.phone.ilike(f"%{client_search}%"))
            )

        if date_from:
            base_query = base_query.where(Purchase.created_at >= date_from)
            count_query = count_query.where(Purchase.created_at >= date_from)
        if date_to:
            base_query = base_query.where(Purchase.created_at <= date_to)
            count_query = count_query.where(Purchase.created_at <= date_to)

        if purchase_type != "all":
            base_query = base_query.where(Purchase.purchase_type == purchase_type)
            count_query = count_query.where(Purchase.purchase_type == purchase_type)

        base_query = base_query.order_by(Purchase.created_at.desc()).limit(per_page).offset(offset)

        total = (await session.execute(count_query)).scalar()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = (await session.execute(base_query)).all()

    purchases = [
        {
            "id": p.id,
            "client_id": p.client_id,
            "client_name": client_name,
            "created_at": p.created_at,
            "total_amount": p.total_amount,
            "purchase_type": p.purchase_type,
            "payment_details": p.payment_details,
        }
        for p, client_name in rows
    ]

    return templates.TemplateResponse("purchases.html", {
        "request": request,
        "purchases": purchases,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "client_search": client_search,
        "date_from": date_from,
        "date_to": date_to,
        "payment_type": payment_type,
        "purchase_type": purchase_type,
        "payment_types": ["cash", "terminal", "qr", "transfer", "invoice", "installment"],
        "purchase_types": ["sale", "preorder", "booking"],
    })


@router.post("/delete/{purchase_id}")
async def delete_purchase(purchase_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        purchase = await session.get(Purchase, purchase_id)
        if purchase:
            await session.delete(purchase)
    return RedirectResponse(url="/admin/purchases", status_code=303)
