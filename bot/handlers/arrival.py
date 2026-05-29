import logging
import re
from typing import List, Dict

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.states import ArrivalConfirmState
from bot.repositories import ItemRepository
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name

logger = logging.getLogger(__name__)
router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


def parse_arrival_text(text: str) -> List[Dict]:
    """Улучшенный парсер. Игнорирует строки-разделители и лучше определяет категории."""
    items = []
    current_category = None
    lines = text.splitlines()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Игнорируем строки-разделители ( -, --, --- и т.д. )
        if re.match(r'^[-–—\s]+$', line):
            continue

        # Строка, которая выглядит как заголовок категории
        if line.endswith(':') or (len(line) < 60 and not any(c.isdigit() for c in line) and not line.startswith(('-', '•'))):
            current_category = line.rstrip(':').strip()
            continue

        if current_category is None:
            current_category = "Без категории"

        # Извлекаем серийный номер
        serial = None
        match = re.search(r'\(([^)]+)\)|SN[:\s]*([A-Za-z0-9-]+)', line, re.IGNORECASE)
        if match:
            serial = match.group(1) or match.group(2)
            text_clean = re.sub(r'\s*\([^)]+\)|\s*SN[:\s]*[A-Za-z0-9-]+', '', line).strip()
        else:
            text_clean = line

        items.append({
            "text": text_clean,
            "category": current_category,
            "serial": serial
        })

    return items


async def determine_category_for_item(item_text: str, existing_categories: list = None) -> str:
    """Улучшенная версия определения категории."""
    stripped = item_text.strip()

    # Приоритет для Б/У и NS
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()

    # Пытаемся найти лучшее совпадение среди существующих категорий
    if existing_categories:
        best_match = None
        best_len = 0
        for cat in existing_categories:
            cat_name = normalize_name(str(cat.get('name') or cat.get('header', ''))).lower().rstrip(':')
            if not cat_name:
                continue
            if base.startswith(cat_name) and len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat.get('name') or cat.get('header')
            elif cat_name in base and len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat.get('name') or cat.get('header')

        if best_match:
            return best_match

    # Fallback для новых товаров
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

    content = None
    if message.document:
        if message.document.file_size > MAX_FILE_SIZE:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                                 text="❌ Файл слишком большой (макс. 10 МБ).",
                                 reply_to_message_id=message.message_id,
                                 message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
            return
        if not (message.document.mime_type == 'text/plain' or message.document.file_name.endswith('.txt')):
            await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                                 text="⚠️ Отправьте текстовый файл .txt",
                                 reply_to_message_id=message.message_id,
                                 message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
            return
        file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        content = file_bytes.read().decode('utf-8', errors='ignore')
    elif message.text or message.caption:
        content = message.text or message.caption
    else:
        return

    parsed_items = parse_arrival_text(content)
    if not parsed_items:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                             text="❌ Не удалось распознать товары.",
                             reply_to_message_id=message.message_id,
                             message_thread_id=config.THREAD_ARRIVAL, delete_after=90)
        return

    # Улучшаем категории с помощью determine_category_for_item
    try:
        existing_cats = await ItemRepository.get_all_categories()  # если есть такой метод
    except:
        existing_cats = []

    for item in parsed_items:
        item['category'] = await determine_category_for_item(item['text'], existing_cats)

    await state.update_data(temp_items=parsed_items)
    await state.set_state(ArrivalConfirmState.waiting_for_confirm)

    preview = f"📥 Прибытие: найдено {len(parsed_items)} товаров\n\n"
    for item in parsed_items[:10]:
        preview += f"• {item['text']}"
        if item.get('serial'):
            preview += f" ({item['serial']})"
        preview += f" → {item['category']}\n"
    if len(parsed_items) > 10:
        preview += f"... и ещё {len(parsed_items)-10} товаров"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Добавить в ассортимент", callback_data="arrival_confirm:yes")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="arrival_confirm:no")]
    ])
    await message.reply(preview, reply_markup=keyboard)


@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("temp_items", [])
    action = callback.data.split(":")[1]

    if action == "yes" and items:
        try:
            added = 0
            for item_data in items:
                await ItemRepository.add_item(
                    text=item_data['text'],
                    serial=item_data.get('serial'),
                    category_name=item_data.get('category', 'Без категории')
                )
                added += 1

            await callback.message.edit_text(f"✅ Успешно добавлено {added} товаров!")
        except Exception as e:
            logger.exception("Ошибка добавления прибытия")
            await callback.message.edit_text(f"❌ Ошибка: {e}")
    else:
        await callback.message.edit_text("❌ Загрузка отменена.")

    await state.clear()
    await callback.answer()
