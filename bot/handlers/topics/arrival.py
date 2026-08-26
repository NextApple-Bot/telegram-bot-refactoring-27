import logging
import os
import re
import tempfile

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.states import ArrivalConfirmState
from bot.models import Category, Item
from bot.repositories.item import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import match_existing_category
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document),
)
async def handle_arrival(message: Message, bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки).",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60,
        )
        return

    lines = []
    if message.document:
        document = message.document
        if document.file_size and document.file_size > MAX_FILE_SIZE:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="❌ Файл слишком большой (макс. 10 МБ).",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60,
            )
            return
        if not (
            document.mime_type == "text/plain"
            or (document.file_name or "").endswith(".txt")
        ):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текстовый файл .txt",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60,
            )
            return
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix="_" + (document.file_name or "arrival.txt"), delete=False
        ) as tmp:
            file_path = tmp.name
        await bot.download(document, destination=file_path)
        try:
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                content = await f.read()
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

        existing_texts = {row._mapping["text"] for row in rows}
        existing_serials = {
            row._mapping["serial"].strip().upper()
            for row in rows
            if row._mapping.get("serial")
        }

        current_categories = await AssortmentService.load_inventory()

        cat_to_items: dict[str, list] = {}
        skipped_duplicates = []
        skipped_no_category = []

        for line in filtered_lines:
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

            # Только существующие категории — новые НЕ создаём
            category_name = match_existing_category(line, current_categories)
            if not category_name:
                skipped_no_category.append(line)
                logger.warning("Нет подходящей категории для: %s", line[:120])
                continue

            cat_to_items.setdefault(category_name, []).append((line, serial))

    if not cat_to_items:
        msg = "❌ Нет новых позиций для добавления."
        if skipped_duplicates:
            msg += f"\n⏭ Дубликаты: {len(skipped_duplicates)}"
        if skipped_no_category:
            msg += (
                f"\n⚠️ Без категории (не добавлены): {len(skipped_no_category)}\n"
                + "\n".join(skipped_no_category[:8])
            )
            if len(skipped_no_category) > 8:
                msg += f"\n… и ещё {len(skipped_no_category) - 8}"
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=msg,
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=90,
        )
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        cat_to_items=cat_to_items,
        skipped_lines=skipped_duplicates,
        skipped_no_serial=skipped_no_serial,
        skipped_no_category=skipped_no_category,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id,
    )

    total_new = sum(len(items) for items in cat_to_items.values())
    response = f"📦 Найдено новых позиций: {total_new}\n"
    response += "Категории:\n"
    for cat_name, items in cat_to_items.items():
        response += f"  • {cat_name}: +{len(items)}\n"
    if skipped_no_serial:
        response += f"⚠️ Без серийного: {len(skipped_no_serial)}\n"
    if skipped_duplicates:
        response += f"⏭ Дубликаты: {len(skipped_duplicates)}\n"
    if skipped_no_category:
        response += f"⚠️ Без подходящей категории (не будут добавлены): {len(skipped_no_category)}\n"
    response += "\nПодтвердите добавление?"

    keyboard = InlineKeyboardMarkup(
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
    await message.reply(response, reply_markup=keyboard)


@router.callback_query(
    ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:")
)
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass

    data = await state.get_data()
    cat_to_items = data.get("cat_to_items") or {}
    action = (callback.data or "").split(":")[-1]

    if action == "yes" and cat_to_items:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            total_inserted = 0
            errors = []
            skipped_cat = []

            # Загружаем id существующих категорий — без создания новых
            rows = (
                await session.execute(select(Category.id, Category.name))
            ).all()
            name_to_id = {r.name: r.id for r in rows}

            for cat_name, items in cat_to_items.items():
                cat_id = name_to_id.get(cat_name)
                if cat_id is None:
                    # точное имя могло отличаться пробелами — ищем
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
