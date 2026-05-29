import logging
import os
import re

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.db import get_pool
from bot.handlers.states import ArrivalConfirmState
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)
router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


async def determine_category_for_item(item_text: str, categories: list) -> str:
    stripped = item_text.strip()
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()
    best_match = None
    best_len = 0

    for cat in categories:
        cat_name = normalize_name(cat.get('header', '')).lower().rstrip(':')
        if not cat_name:
            continue

        if base.startswith(cat_name):
            remainder = base[len(cat_name):]
            if (remainder == '' or remainder.startswith(' ')) and len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat['header']
        elif cat_name in base:
            if len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat['header']

    if best_match:
        return best_match

    if 'iphone' in item_text.lower():
        return f"{extract_base_name(item_text)}:"

    if ',' in item_text:
        new_header = item_text.split(',')[0].strip() + ':'
    else:
        words = item_text.split()
        new_header = ' '.join(words[:2]).strip() + ':'

    return normalize_name(new_header)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot, chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL, delete_after=60
        )
        return

    # === Получение контента ===
    lines = []
    if message.document:
        if message.document.file_size > MAX_FILE_SIZE:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                                 text="❌ Файл слишком большой.", delete_after=60)
            return
        file_path = f"/tmp/{message.document.file_name}"
        await message.bot.download(message.document, destination=file_path)
        try:
            async with aiofiles.open(file_path, encoding='utf-8') as f:
                content = await f.read()
            lines = [line.strip() for line in content.splitlines() if line.strip()]
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption
        if content:
            lines = [line.strip() for line in content.splitlines() if line.strip()]

    if not lines:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                             text="⚠️ Отправьте текст или .txt файл.", delete_after=60)
        return

    # Убираем строки-разделители
    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]

    # Фильтруем только строки с серийным номером
    filtered_lines = []
    skipped_no_serial = []
    for line in lines:
        if extract_serials(line):
            filtered_lines.append(line)
        else:
            skipped_no_serial.append(line)

    if not filtered_lines:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                             text="❌ Нет строк с серийным номером.", delete_after=60)
        return

    # Проверка дубликатов
    existing_items = await ItemRepository.get_all_items_serials()
    existing_texts = {item['text'] for item in existing_items}
    existing_serials = {item['serial'].upper() for item in existing_items if item.get('serial')}

    current_categories = await AssortmentService.load_inventory()

    cat_to_items = {}
    skipped_duplicates = []

    for line in filtered_lines:
        if line in existing_texts:
            skipped_duplicates.append(line)
            continue

        serials = extract_serials(line)
        serial = serials[0].upper() if serials else None
        if serial and serial in existing_serials:
            skipped_duplicates.append(line)
            continue

        category_name = await determine_category_for_item(line, current_categories)
        cat_to_items.setdefault(category_name, []).append((line, serial))

    if not cat_to_items:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                             text="❌ Нет новых товаров для добавления.", delete_after=60)
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        cat_to_items=cat_to_items,
        skipped_duplicates=skipped_duplicates,
        skipped_no_serial=skipped_no_serial
    )

    total = sum(len(v) for v in cat_to_items.values())
    text = f"📦 Найдено новых товаров: **{total}**\n"
    if skipped_duplicates:
        text += f"⏭ Дубликаты: {len(skipped_duplicates)}\n"
    if skipped_no_serial:
        text += f"⚠️ Без серийника: {len(skipped_no_serial)}\n"
    text += "\nПодтвердить добавление?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm:yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_confirm:no")]
    ])
    await message.reply(text, reply_markup=keyboard)


@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat_to_items = data.get("cat_to_items", {})
    action = callback.data.split(":")[1]

    if action != "yes":
        await callback.message.edit_text("❌ Добавление отменено.")
        await state.clear()
        return

    pool = await get_pool()
    total_added = 0
    failed = []

    for cat_name, items in cat_to_items.items():
        try:
            cat_id = await ItemRepository.get_or_create_category(cat_name)
            for text, serial in items:
                is_booked = 'Бронь от' in text
                try:
                    async with pool.acquire() as conn:
                        await conn.execute('''
                            INSERT INTO items (text, serial, category_id, is_booked)
                            VALUES ($1, $2, $3, $4)
                        ''', text, serial, cat_id, is_booked)
                    total_added += 1
                except Exception as e:
                    logger.error(f"Ошибка добавления: {text} | {e}")
                    failed.append(text)
        except Exception as e:
            logger.exception(f"Ошибка с категорией {cat_name}")
            for text, _ in items:
                failed.append(text)

    await AssortmentService.invalidate_cache()

    if total_added > 0 and not failed:
        await callback.message.edit_text(f"✅ Успешно добавлено {total_added} товаров!")
    elif total_added > 0:
        msg = f"✅ Добавлено: {total_added}\n❌ Не удалось добавить:\n"
        for item in failed[:6]:
            msg += f"• {item}\n"
        if len(failed) > 6:
            msg += f"... и ещё {len(failed)-6}"
        await callback.message.edit_text(msg)
    else:
        await callback.message.edit_text("❌ Не удалось добавить ни одного товара.")

    await state.clear()
    await callback.answer()
