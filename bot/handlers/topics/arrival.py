# bot/handlers/topics/arrival.py
import logging
import os
import re
import tempfile

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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

    # fallback
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
    """Основной обработчик поступления товаров (v26 + улучшения v27)."""
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

    lines = []

    # === Чтение файла или текста ===
    if message.document:
        if message.document.file_size and message.document.file_size > MAX_FILE_SIZE:
            await send_and_clean(message.bot, message.chat.id, "❌ Файл слишком большой (макс. 10 МБ).", delete_after=60)
            return

        file_path = f"/tmp/{message.document.file_name}"
        await message.bot.download(message.document, destination=file_path)

        try:
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                content = await f.read()
                lines = [line.strip() for line in content.splitlines() if line.strip()]
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption or ""
        lines = [line.strip() for line in content.splitlines() if line.strip()]

    # Убираем пустые разделители
    lines = [l for l in lines if not re.match(r'^\s*-+\s*$', l)]

    # === Склеивание строк (самая важная фича v26) ===
    merged_lines = []
    i = 0
    while i < len(lines):
        if not extract_serials(lines[i]) and i + 1 < len(lines) and extract_serials(lines[i + 1]):
            merged_lines.append(f"{lines[i]} {lines[i + 1]}")
            i += 2
        else:
            merged_lines.append(lines[i])
            i += 1
    lines = merged_lines

    # === Фильтрация и сбор статистики ===
    filtered_lines = []
    skipped_no_serial = []
    for line in lines:
        if extract_serials(line):
            filtered_lines.append(line)
        else:
            skipped_no_serial.append(line)

    if not filtered_lines:
        await send_and_clean(message.bot, message.chat.id, "❌ Нет ни одной строки с серийным номером.", delete_after=60)
        return

    # === Проверка дубликатов ДО подтверждения (v26) ===
    async_session = get_async_session_factory()
    async with async_session() as session:
        existing_items = (await session.execute(
            select(Item.text, Item.serial)
        )).all()

        existing_texts = {item.text.strip() for item in existing_items}
        existing_serials = {item.serial.strip().upper() for item in existing_items if item.serial}

        current_categories = await AssortmentService.load_inventory()

        cat_to_items = {}
        skipped_duplicates = []

        for line in filtered_lines:
            if line in existing_texts:
                skipped_duplicates.append(f"[Дубликат текста] {line}")
                continue

            serials = extract_serials(line)
            serial = serials[0].
