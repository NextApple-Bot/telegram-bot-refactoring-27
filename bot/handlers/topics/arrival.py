import asyncio
import logging
import os
import re
import tempfile
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.topics.filters import in_arrival, in_main_group
from bot.models import Category, Item
from bot.services.assortment import AssortmentService
from bot.handlers.states import ArrivalConfirmState
from bot.utils.message import send_and_clean
from bot.utils.sort import match_existing_category, normalize_item_text
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)
router = Router(name="arrival")


def _format_skipped_block(title: str, items: list, limit: int = 8) -> str:
    if not items:
        return ""
    lines = [f"\n{title} ({len(items)}):"]
    for it in items[:limit]:
        lines.append(f"• {it}")
    if len(items) > limit:
        lines.append(f"… и ещё {len(items) - limit}")
    return "\n".join(lines)


@router.message(in_main_group, in_arrival, F.text | F.document | F.photo, StateFilter("*"))
async def handle_arrival_message(message: Message, state: FSMContext, bot: Bot) -> None:
    current = await state.get_state()
    if current == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки).",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=30,
        )
        return

    lines: list[str] = []

    if message.document:
        doc = message.document
        if doc.file_size and doc.file_size > 10 * 1024 * 1024:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="❌ Файл слишком большой (макс. 10 МБ).",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60,
            )
            return
        file_name = (doc.file_name or "").lower()
        if not file_name.endswith(".txt"):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текстовый файл .txt",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60,
            )
            return
        file = await bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            file_path = tmp.name
        try:
            await bot.download_file(file.file_path, file_path)
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            lines = [line.strip() for line in content.splitlines() if line.strip()]
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption
        if not content:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текст, файл или фото с подписью.",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60,
            )
            return
        lines = [line.strip() for line in content.splitlines() if line.strip()]

    lines = [line for line in lines if not re.match(r"^\s*-+\s*$", line)]

    merged_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            not extract_serials(line)
            and not line.strip().endswith(":")
            and i + 1 < len(lines)
            and extract_serials(lines[i + 1])
        ):
            merged_lines.append(f"{line} {lines[i + 1]}")
            i += 2
        else:
            merged_lines.append(line)
            i += 1
    lines = merged_lines

    filtered_lines = []
    skipped_no_serial = []
    for line in lines:
        serials = extract_serials(line)
        if serials:
            filtered_lines.append(line)
        else:
            skipped_no_serial.append(line)
            logger.info("Пропущена строка без серийного номера: %s", line)

    if not filtered_lines:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="❌ Нет ни одной строки с серийным номером. Добавление отменено.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60,
        )
        return

    async_session = get_async_session_factory()
    async with async_session() as session:
        result = await session.execute(select(Item.text, Item.serial))
        rows = result.all()

        existing_texts = {
            (row._mapping["text"] or "").strip()
            for row in rows
            if row._mapping.get("text")
        }
        existing_serials = {
            row._mapping["serial"].strip().upper()
            for row in rows
            if row._mapping.get("serial")
        }

        cats_result = await session.execute(
            select(Category.id, Category.name).where(Category.name != "__SYSTEM__")
        )
        current_categories = [
            {"header": r.name, "name": r.name, "id": r.id} for r in cats_result.all()
        ]

        cat_to_items: dict[str, list] = {}
        skipped_duplicates = []
        skipped_no_category = []

        for line in filtered_lines:
            line = normalize_item_text(line)
            if line in existing_texts:
                skipped_duplicates.append(f"[Дубликат текста] {line}")
                continue
            serials = extract_serials(line)
            if not serials:
                continue
            serial = serials[0].strip().upper()
            if serial in existing_serials:
                skipped_duplicates.append(f"[Дубликат серийного {serial}] {line}")
                continue

            category_name = match_existing_category(line, current_categories)
            if not category_name:
                skipped_no_category.append(line)
                logger.warning("Нет подходящей категории для: %s", line[:120])
                continue

            cat_to_items.setdefault(category_name, []).append((line, serial))

    if not cat_to_items:
        msg = "❌ Нет новых позиций для добавления.\n"
        if skipped_duplicates:
            msg += _format_skipped_block("⏭ Дубликаты", skipped_duplicates, limit=10)
        if skipped_no_category:
            msg += _format_skipped_block(
                "⚠️ Нет категории", skipped_no_category, limit=10
            )
        if skipped_no_serial:
            msg += _format_skipped_block(
                "⚠️ Без серийного номера", skipped_no_serial, limit=10
            )
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=msg.strip(),
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=90,
        )
        return

    preview_lines = []
    total_new = 0
    for cat, items in cat_to_items.items():
        preview_lines.append(f"• {cat}: +{len(items)}")
        total_new += len(items)

    msg = f"📦 К добавлению: {total_new}\n\n" + "\n".join(preview_lines)
    if skipped_no_serial:
        msg += _format_skipped_block(
            "⚠️ Без серийного номера (пропущены)",
            skipped_no_serial,
            limit=5,
        )
    if skipped_duplicates:
        msg += _format_skipped_block(
            "⏭ Дубликаты (пропущены)",
            skipped_duplicates,
            limit=5,
        )
    if skipped_no_category:
        msg += _format_skipped_block(
            "⚠️ Нет категории (пропущены)",
            skipped_no_category,
            limit=5,
        )
    msg += "\n\nПодтвердите добавление?"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="arrival_confirm:yes"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="arrival_confirm:no"
                ),
            ]
        ]
    )

    # store for confirm
    payload = {
        str(cat): [[t, s] for t, s in items] for cat, items in cat_to_items.items()
    }
    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(cat_to_items=payload)

    await message.answer(msg, reply_markup=kb)


@router.callback_query(F.data.startswith("arrival_confirm:"), ArrivalConfirmState.waiting_for_confirm)
async def arrival_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    cat_to_items_raw = data.get("cat_to_items") or {}
    cat_to_items = {
        cat: [(t, s) for t, s in items] for cat, items in cat_to_items_raw.items()
    }

    if action == "yes":
        total_inserted = 0
        skipped_cat = []
        errors = []
        async_session = get_async_session_factory()
        async with async_session() as session:
            rows = (
                await session.execute(select(Category.id, Category.name))
            ).all()
            name_to_id = {r.name: r.id for r in rows}

            for cat_name, items in cat_to_items.items():
                cat_id = name_to_id.get(cat_name)
                if cat_id is None:
                    for n, cid in name_to_id.items():
                        if n.rstrip(":").strip().lower() == cat_name.rstrip(":").strip().lower():
                            cat_id = cid
                            break
                if cat_id is None:
                    skipped_cat.append(cat_name)
                    logger.error("Категория не найдена в БД (не создаём): %s", cat_name)
                    continue

                for text_val, serial in items:
                    is_booked = "бронь" in (text_val or "").lower()
                    try:
                        session.add(
                            Item(
                                text=text_val,
                                serial=serial,
                                category_id=cat_id,
                                is_booked=is_booked,
                            )
                        )
                        total_inserted += 1
                    except Exception as e:
                        errors.append(f"{text_val[:60]}: {e}")

            await session.commit()

        await AssortmentService.invalidate_cache()
        msg = f"✅ Добавлено {total_inserted} товаров."
        if skipped_cat:
            msg += f"\n⚠️ Категории не найдены (пропущено): {', '.join(skipped_cat)}"
        if errors:
            msg += f"\nОшибок: {len(errors)}"
        await callback.message.edit_text(msg)

        if errors:
            await send_and_clean(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text="\n".join(errors[:5]),
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60,
            )
    elif action == "no":
        await callback.message.edit_text("❌ Добавление отменено.")

    await state.clear()
