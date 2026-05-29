from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from bot.db import get_async_session_factory
from bot.models import Seller
from web_admin.templates import templates

router = APIRouter()


@router.get("/manage")
async def seller_manage(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        sellers = (await session.execute(select(Seller).order_by(Seller.name))).scalars().all()
    return templates.TemplateResponse("sellers_manage.html", {"request": request, "sellers": sellers})


@router.post("/add")
async def add_seller(request: Request, name: str = Form(...)):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        session.add(Seller(name=name))
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        seller = await session.get(Seller, seller_id)
        if seller:
            await session.delete(seller)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.get("/stats")
async def seller_stats(
    request: Request,
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=365),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    return templates.TemplateResponse("sellers_stats.html", {
        "request": request,
        "mode": mode,
        "target_date": target_date or "",
        "days": days,
        "results": [],
    })
