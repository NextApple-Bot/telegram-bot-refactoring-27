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
    sort_by: str = Query("id", pattern="^(id|client_name|created_at|total_amount|purchase_type)$"),
   
