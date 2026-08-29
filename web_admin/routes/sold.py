"""
Проданные товары + отмена продажи одной кнопкой.

Отмена:
  1) товар снова в ассортименте
  2) Sale и DailyPayment по sale_message_id удаляются (статистика откатывается)
  3) DeletedItem помечается / удаляется
  4) в топик продаж уходит «❌ Отмена продажи»

«Отменить все продажи» — массовая отмена всех проданных позиций
с двухэтапным подтверждением (ввод слова ОТМЕНИТЬ).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from aiogram import Bot
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select

from bot import config
from bot.db import get_async_session_factory
from bot.models import DailyPayment, DeletedItem, Item, Sale
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_sale_reason(reason: str | None) -> bool:
    r = (reason or "").lower()
    if not r:
        return True
    return "sale" in r or r in ("sold", "продан")


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
async def cancel_sale(deleted_id: int):
    """
    Отмена продажи / восстановление в ассортимент (одна кнопка).
    """
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
                        url="/admin/sold?err=Запись+не+найдена",
                        status_code=303,
                    )

                if deleted.restored:
                    return RedirectResponse(
                        url="/admin/sold?err=Уже+восстановлено",
                        status_code=303,
                    )

                item_text = deleted.text or ""
                serial = (deleted.serial or "").strip() or None
                sale_message_id = deleted.sale_message_id
                original_item_id = deleted.item_id
                category_id = deleted.category_id

                # Серийник уже снова в складе?
                if serial:
                    exists = await session.scalar(
                        select(Item.id).where(Item.serial == serial).limit(1)
                    )
                    if exists:
                        serial_for_item = None
                        logger.warning(
                            "При отмене продажи serial=%s уже в items — восстанавливаем без serial",
                            serial,
                        )
                    else:
                        serial_for_item = serial
                else:
                    serial_for_item = None

                session.add(
                    Item(
                        text=item_text,
                        serial=serial_for_item,
                        category_id=category_id,
                        is_booked=False,
                        is_sold=False,
                    )
                )

                if sale_message_id:
                    await session.execute(
                        delete(Sale).where(Sale.message_id == sale_message_id)
                    )
                    await session.execute(
                        delete(DailyPayment).where(
                            DailyPayment.sale_message_id == sale_message_id
                        )
                    )
                elif original_item_id:
                    await session.execute(
                        delete(Sale).where(Sale.item_id == original_item_id)
                    )

                deleted.restored = True
                await session.delete(deleted)

                logger.info(
                    "Отмена продажи deleted_id=%s item_id=%s sale_message_id=%s serial=%s",
                    deleted_id,
                    original_item_id,
                    sale_message_id,
                    serial,
                )

        try:
            await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        except Exception:
            pass
        await AssortmentService.invalidate_cache()

        # Уведомление в топик (после коммита)
        asyncio.create_task(
            _notify_cancel(item_text, serial or "", sale_message_id)
        )

        return RedirectResponse(
            url="/admin/sold?ok=Продажа+отменена.+Товар+вернулся+в+ассортимент",
            status_code=303,
        )
    except Exception as e:
        logger.exception("Ошибка отмены продажи deleted_id=%s", deleted_id)
        return RedirectResponse(
            url=f"/admin/sold?err={str(e)[:80]}",
            status_code=303,
        )


@router.post("/cancel-all")
async def cancel_all_sales(confirm: str = Form("...")):
    """
    Массовая отмена ВСЕХ продаж.
    Требует двухэтапного подтверждения: confirm == 'ОТМЕНИТЬ'.
    """
    if (confirm or "").strip().upper() != "ОТМЕНИТЬ":
        return RedirectResponse(
            url="/admin/sold?err=Для+отмены+всех+продаж+введите+слово+ОТМЕНИТЬ",
            status_code=303,
        )

    async_session = get_async_session_factory()
    cancelled = 0
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
                        select(DeletedItem).where(base_filter, DeletedItem.restored.is_(False))
                    )
                ).scalars().all()

                for deleted in rows:
                    item_text = deleted.text or ""
                    serial = (deleted.serial or "").strip() or None
                    sale_message_id = deleted.sale_message_id
                    original_item_id = deleted.item_id
                    category_id = deleted.category_id

                    if serial:
                        exists = await session.scalar(
                            select(Item.id).where(Item.serial == serial).limit(1)
                        )
                        serial_for_item = None if exists else serial
                    else:
                        serial_for_item = None

                    session.add(
                        Item(
                            text=item_text,
                            serial=serial_for_item,
                            category_id=category_id,
                            is_booked=False,
                            is_sold=False,
                        )
                    )

                    if sale_message_id:
                        await session.execute(
                            delete(Sale).where(Sale.message_id == sale_message_id)
                        )
                        await session.execute(
                            delete(DailyPayment).where(
                                DailyPayment.sale_message_id == sale_message_id
                            )
                        )
                    elif original_item_id:
                        await session.execute(
                            delete(Sale).where(Sale.item_id == original_item_id)
                        )

                    deleted.restored = True
                    await session.delete(deleted)
                    cancelled += 1
                    restored_items.append((item_text, serial, sale_message_id))

                logger.info("Массовая отмена продаж: отменено %s шт.", cancelled)

        try:
            await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        except Exception:
            pass
        await AssortmentService.invalidate_cache()

        if cancelled:
            asyncio.create_task(_notify_cancel_all(cancelled, restored_items))

        return RedirectResponse(
            url=f"/admin/sold?ok=Отменено+продаж:+{cancelled}.+Товары+вернулись+в+ассортимент",
            status_code=303,
        )
    except Exception as e:
        logger.exception("Ошибка массовой отмены продаж")
        return RedirectResponse(
            url=f"/admin/sold?err={str(e)[:80]}",
            status_code=303,
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
        text = "\n".join(lines)
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
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
        # Показываем первые 10 позиций, чтобы не раздувать сообщение
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
