"""
Проданные товары + отмена продажи одной кнопкой.

Отмена (через bot.services.cancel_sale.cancel_one_deleted_sale):
  1) товар снова в ассортименте
  2) Sale и DailyPayment по sale_message_id удаляются
  3) DeletedItem удаляется
  4) в топик продаж уходит «❌ Отмена продажи»
  5) StatsAdjustment за день продажи сбрасывается

«Отменить все продажи» — массовая отмена с подтверждением ОТМЕНИТЬ.
«Отменить за период» — безопаснее, только выбранные даты.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time as dtime

from aiogram import Bot
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select

from bot import config
from bot.db import get_async_session_factory
from bot.models import DeletedItem
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from bot.services.cancel_sale import cancel_one_deleted_sale
from web_admin.services.day_stats import clear_adjustments_for_dates
from web_admin.templates import templates
from web_admin.services.audit import log_admin_action

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def list_sold(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    q: str = Query("", max_length=120),
):
    flash = request.query_params.get("ok") or request.query_params.get("err")
    flash_ok = bool(request.query_params.get("ok"))
    flash_msg = request.query_params.get("ok") or request.query_params.get("err") or ""

    async_session = get_async_session_factory()
    async with async_session() as session:
        offset = (page - 1) * per_page

        base_filter = or_(
            DeletedItem.reason.ilike("%sale%"),
            DeletedItem.sale_message_id.isnot(None),
            DeletedItem.reason.is_(None),
        )

        filters = [base_filter]
        query = (q or "").strip()
        if query:
            like = f"%{query}%"
            filters.append(
                or_(
                    DeletedItem.text.ilike(like),
                    DeletedItem.serial.ilike(like),
                )
            )

        count_q = select(func.count()).select_from(DeletedItem).where(*filters)
        total = (await session.execute(count_q)).scalar() or 0
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        rows_q = (
            select(DeletedItem)
            .where(*filters)
            .order_by(DeletedItem.deleted_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        items = (await session.execute(rows_q)).scalars().all()

    return templates.TemplateResponse(
        "sold.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "q": query,
            "flash_ok": flash_ok if flash else None,
            "flash_msg": flash_msg,
        },
    )


@router.post("/cancel/{deleted_id}")
@router.post("/restore/{deleted_id}")
async def cancel_sale(request: Request, deleted_id: int):
    async_session = get_async_session_factory()
    item_text = ""
    serial = ""
    sale_message_id = None

    try:
        async with async_session() as session:
            async with session.begin():
                deleted = await session.get(DeletedItem, deleted_id)
                if not deleted:
                    return RedirectResponse(
                        url="/admin/sold?err=Запись+не+найдена", status_code=303
                    )
                if deleted.restored:
                    return RedirectResponse(
                        url="/admin/sold?err=Уже+восстановлено", status_code=303
                    )

                meta = await cancel_one_deleted_sale(session, deleted)
                item_text = meta["item_text"]
                serial = meta["serial"] or ""
                sale_message_id = meta["sale_message_id"]
                day_for_adj = meta["day"]

                if day_for_adj:
                    await clear_adjustments_for_dates(session, [day_for_adj])

                logger.info(
                    "Отмена продажи deleted_id=%s day=%s",
                    deleted_id,
                    day_for_adj,
                )

        try:
            await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        except Exception:
            pass
        await AssortmentService.invalidate_cache()

        asyncio.create_task(
            _notify_cancel(item_text, serial or "", sale_message_id)
        )

        await log_admin_action("cancel_one", request=request, deleted_id=deleted_id)

        return RedirectResponse(
            url="/admin/sold?ok=Продажа+отменена.+Товар+вернулся+в+ассортимент",
            status_code=303,
        )
    except ValueError as e:
        if str(e) == "already_restored":
            return RedirectResponse(
                url="/admin/sold?err=Уже+восстановлено", status_code=303
            )
        logger.exception("Ошибка отмены продажи deleted_id=%s", deleted_id)
        return RedirectResponse(
            url=f"/admin/sold?err={str(e)[:80]}", status_code=303
        )
    except Exception as e:
        logger.exception("Ошибка отмены продажи deleted_id=%s", deleted_id)
        return RedirectResponse(
            url=f"/admin/sold?err={str(e)[:80]}", status_code=303
        )


@router.post("/cancel-all")
async def cancel_all_sales(request: Request, confirm: str = Form("")):
    if (confirm or "").strip().upper() != "ОТМЕНИТЬ":
        return RedirectResponse(
            url="/admin/sold?err=Для+отмены+всех+продаж+введите+слово+ОТМЕНИТЬ",
            status_code=303,
        )

    async_session = get_async_session_factory()
    cancelled = 0
    restored_items: list[tuple[str, str | None, int | None]] = []
    affected_days: set = set()

    try:
        async with async_session() as session:
            async with session.begin():
                base_filter = or_(
                    DeletedItem.reason.ilike("%sale%"),
                    DeletedItem.sale_message_id.isnot(None),
                    DeletedItem.reason.is_(None),
                )
                rows = (
                    await session.execute(
                        select(DeletedItem).where(
                            base_filter, DeletedItem.restored.is_(False)
                        )
                    )
                ).scalars().all()

                for deleted in rows:
                    meta = await cancel_one_deleted_sale(session, deleted)
                    cancelled += 1
                    restored_items.append(
                        (meta["item_text"], meta["serial"], meta["sale_message_id"])
                    )
                    if meta["day"]:
                        affected_days.add(meta["day"])

                if affected_days:
                    await clear_adjustments_for_dates(session, affected_days)

                logger.info(
                    "Массовая отмена: %s шт., adj days=%s",
                    cancelled,
                    len(affected_days),
                )

        try:
            await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        except Exception:
            pass
        await AssortmentService.invalidate_cache()

        if cancelled:
            asyncio.create_task(_notify_cancel_all(cancelled, restored_items))

        await log_admin_action("cancel_all", request=request, cancelled=cancelled)

        return RedirectResponse(
            url=f"/admin/sold?ok=Отменено+продаж:+{cancelled}.+Товары+вернулись+в+ассортимент",
            status_code=303,
        )
    except Exception as e:
        logger.exception("Ошибка массовой отмены продаж")
        return RedirectResponse(
            url=f"/admin/sold?err={str(e)[:80]}", status_code=303
        )


@router.post("/cancel-period")
async def cancel_sales_period(
    request: Request,
    date_from: str = Form(...),
    date_to: str = Form(...),
    confirm: str = Form(""),
):
    """Отмена продаж за период (по deleted_at). Подтверждение: ОТМЕНИТЬ."""
    if (confirm or "").strip().upper() != "ОТМЕНИТЬ":
        return RedirectResponse(
            url="/admin/sold?err=Для+отмены+за+период+введите+слово+ОТМЕНИТЬ",
            status_code=303,
        )
    try:
        start = datetime.strptime(str(date_from)[:10], "%Y-%m-%d").date()
        end = datetime.strptime(str(date_to)[:10], "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(url="/admin/sold?err=Неверные+даты", status_code=303)
    if end < start:
        start, end = end, start

    start_dt = datetime.combine(start, dtime.min)
    end_dt = datetime.combine(end, dtime.max)

    async_session = get_async_session_factory()
    cancelled = 0
    affected_days: set = set()
    restored_items: list[tuple[str, str | None, int | None]] = []

    try:
        async with async_session() as session:
            async with session.begin():
                base_filter = or_(
                    DeletedItem.reason.ilike("%sale%"),
                    DeletedItem.sale_message_id.isnot(None),
                    DeletedItem.reason.is_(None),
                )
                rows = (
                    await session.execute(
                        select(DeletedItem).where(
                            base_filter,
                            DeletedItem.restored.is_(False),
                            DeletedItem.deleted_at >= start_dt,
                            DeletedItem.deleted_at <= end_dt,
                        )
                    )
                ).scalars().all()

                for deleted in rows:
                    meta = await cancel_one_deleted_sale(session, deleted)
                    cancelled += 1
                    restored_items.append(
                        (meta["item_text"], meta["serial"], meta["sale_message_id"])
                    )
                    if meta["day"]:
                        affected_days.add(meta["day"])

                if affected_days:
                    await clear_adjustments_for_dates(session, affected_days)

                logger.info(
                    "Отмена за период %s..%s: %s шт., adj days=%s",
                    start,
                    end,
                    cancelled,
                    len(affected_days),
                )

        try:
            await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        except Exception:
            pass
        await AssortmentService.invalidate_cache()

        if cancelled:
            asyncio.create_task(_notify_cancel_all(cancelled, restored_items))

        await log_admin_action(
            "cancel_period",
            request=request,
            date_from=date_from,
            date_to=date_to,
            cancelled=cancelled,
        )

        return RedirectResponse(
            url=f"/admin/sold?ok=Отменено+за+период:+{cancelled}",
            status_code=303,
        )
    except Exception as e:
        logger.exception("Ошибка отмены за период")
        return RedirectResponse(
            url=f"/admin/sold?err={str(e)[:80]}", status_code=303
        )


async def _notify_cancel(
    item_text: str,
    serial: str,
    sale_message_id: int | None,
) -> None:
    try:
        bot = Bot(token=config.BOT_TOKEN)
        lines = ["❌ Отмена продажи:", ""]
        title = (item_text or "").strip()
        if serial and f"({serial})" not in title:
            lines.append(f"{title} ({serial})")
        else:
            lines.append(title or "—")
        lines.append("")
        lines.append("Товар возвращён в ассортимент. Статистика продажи откатана.")
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text="\n".join(lines),
            message_thread_id=config.THREAD_SALES,
        )
        await bot.session.close()
    except Exception as e:
        logger.error("Не удалось отправить уведомление об отмене продажи: %s", e)


async def _notify_cancel_all(
    count: int,
    items: list[tuple[str, str | None, int | None]],
) -> None:
    try:
        bot = Bot(token=config.BOT_TOKEN)
        lines = [
            "❌ Отменены все продажи",
            "",
            f"Всего отменено: {count}",
            "",
            "Товары возвращены в ассортимент. Статистика откатана.",
        ]
        preview = items[:10]
        if preview:
            lines.append("")
            lines.append("Примеры:")
            for text, serial, _ in preview:
                t = (text or "—").strip()
                if serial and f"({serial})" not in t:
                    t = f"{t} ({serial})"
                lines.append(f"• {t}")
            if len(items) > 10:
                lines.append(f"… и ещё {len(items) - 10}")
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text="\n".join(lines),
            message_thread_id=config.THREAD_SALES,
        )
        await bot.session.close()
    except Exception as e:
        logger.error("Не удалось отправить уведомление о массовой отмене: %s", e)
