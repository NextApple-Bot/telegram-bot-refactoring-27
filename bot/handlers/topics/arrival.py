# bot/handlers/topics/arrival.py
import logging
import os
import re

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.states import ArrivalConfirmState
from bot.models import Item
from bot.repositories.item import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


def is_booked_item(text: str) -> bool:
    """Точная проверка, является ли товар забронированным."""
    if not text:
        return False
    return "бронь" in text.lower()


async def determine_category_for_item(item_text: str, existing_categories: list) -> str:
    """Умное определение категории (полностью из v26)."""
    stripped = item_text.strip()

    if stripped.startswith(("Б/У -", "Б/У ")):
        return "Б/У:"
    if stripped.startswith(("NS -", "NS ")):
        return "NS:"

    base = extract_base_name(item_text).lower()
    best_match = None
    best_len = 0

    for cat in existing_categories:
        cat_name = normalize_name(cat.get('header', '')).lower().rstrip(':')
        if not cat_name:
            continue
        if base.startswith(cat_name):
            remainder = base[len(cat_name):]
            if (remainder == '' or remainder[0] == ' ') and len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat['header']

    if best_match:
        return best_match

    if ',' in item_text:
        new_header = item_text.split(',')[0].strip() + ':'
    else:
        words = item_text.split()[:2]
        new_header = ' '.join(words).strip() + ':'

    return normalize_name(new_header)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, state: FSMContext):
    """Полноценный обработчик поступления товаров."""
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60
        )
        return

    # ... (весь код до проверки дубликатов остаётся без изменений) ...

    lines = []  # ← здесь идёт вся предобработка строк (склеивание и т.д.)

    # === Чтение данных (опущено для краткости — остаётся как было) ===
    # ... код чтения файла/текста, склеивания, фильтрации ...

    if not filtered_lines:
        await send_and_clean(message.bot, message.chat.id, "❌ Нет ни одной строки с серийным номером.", delete_after=60)
        return

    # === КРИТИЧЕСКИЙ БЛОК: проверка дубликатов с защитой ===
    cat_to_items = {}
    skipped_duplicates = []
    skipped_no_serial = []  # уже есть выше

    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            existing_items = (await session.execute(
                select(Item.text, Item.serial)
            )).all()

            existing_texts = {item.text.strip() for item in existing_items}
            existing_serials = {item.serial.strip().upper() for item in existing_items if item.serial}

            current_categories = await AssortmentService.load_inventory()

            for line in filtered_lines:
                if line in existing_texts:
                    skipped_duplicates.append(f"[Дубликат текста] {line}")
                    continue

                serials = extract_serials(line)
                serial = serials[0].strip().upper() if serials else None

                if serial and serial in existing_serials:
                    skipped_duplicates.append(f"[Дубликат серийника {serial}] {line}")
                    continue

                category_name = await determine_category_for_item(line, current_categories)
                cat_to_items.setdefault(category_name, []).append((line, serial))

        logger.info(f"✅ Проверка дубликатов завершена: "
                   f"дубликатов={len(skipped_duplicates)}, "
                   f"новых позиций={sum(len(v) for v in cat_to_items.values())}")

    except Exception as e:
        logger.exception("❌ Ошибка при проверке дубликатов в arrival (БД)")
        # Fallback: добавляем все товары как новые
        cat_to_items = {}
        for line in filtered_lines:
            serials = extract_serials(line)
            serial = serials[0].strip().upper() if serials else None
            category_name = await determine_category_for_item(line, await AssortmentService.load_inventory())
            cat_to_items.setdefault(category_name, []).append((line, serial))

        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Не удалось проверить дубликаты (проблема с БД). Добавляем все товары как новые.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=45
        )

    # === Дальше идёт FSM подтверждения (без изменений) ===
    if not cat_to_items:
        await send_and_clean(message.bot, message.chat.id, "❌ Нет новых позиций (все дубликаты).", delete_after=60)
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        cat_to_items=cat_to_items,
        skipped_duplicates=skipped_duplicates,
        skipped_no_serial=skipped_no_serial,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id
    )

    total_new = sum(len(items) for items in cat_to_items.values())
    text = (
        f"📦 Найдено **новых** позиций: {total_new}\n"
        f"⏭ Пропущено (дубликаты): {len(skipped_duplicates)}\n"
        f"⚠️ Пропущено (без серийного номера): {len(skipped_no_serial)}\n\n"
        "Подтверждаете добавление в ассортимент?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm:yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_confirm:no")
    ]])

    await message.reply(text, reply_markup=keyboard)


# process_arrival_confirm остаётся без изменений
@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    pass
