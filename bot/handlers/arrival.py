import logging
import re
from typing import List, Dict

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.states import ArrivalConfirmState
from bot.models import Category
from bot.repositories import ItemRepository
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name

logger = logging.getLogger(__name__)
router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


def parse_arrival_text(text: str) -> List[Dict]:
    """Парсер с улучшенной фильтрацией разделителей"""
    items = []
    current_category = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Пропускаем строки-разделители
        if re.match(r'^[-–—\s]+$', line):
            continue

        # Определяем заголовок категории
        if line.endswith(':') or (len(line) < 55 and not any(c.isdigit() for c in line)):
            current_category = line.rstrip(':').strip()
            continue

        if current_category is None:
            current_category = "Без категории"

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


async def get_all_categories() -> List[Dict]:
    """Получает все категории из базы"""
    async with get_async_session_factory()() as session:
        result = await session.execute(select(Category.id, Category.name))
        return [{"id": row.id, "name": row.name} for row in result.all()]


async def get_or_create_category(name: str) -> int:
    """Создаёт категорию, если её нет"""
    async with get_async_session_factory()() as session:
        cat = await session.scalar(select(Category).where(Category.name.ilike(name)))
        if cat:
            return cat.id

        new_cat = Category(name=name)
        session.add(new_cat)
        await session.commit()
        await session.refresh(new_cat)
        return new_cat.id


async def determine_category_for_item(item_text: str, existing_categories: List[Dict]) -> str:
    """
    Умный поиск категории:
    1. Сначала ищет лучшее совпадение среди существующих категорий
    2. Если не нашёл — создаёт новую осмысленную категорию
    """
    stripped = item_text.strip()

    # Приоритет для специальных категорий
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()

    # === УМНЫЙ ПОИСК СРЕДИ СУЩЕСТВУЮЩИХ КАТЕГОРИЙ ===
    best_match = None
    best_score = 0

    for cat in existing_categories:
        cat_name = normalize_name(cat['name']).lower().rstrip(':')
        if not cat_name:
            continue

        score = 0
        if base.startswith(cat_name):
            score = len(cat_name) + 10
        elif cat_name in base:
            score = len(cat_name)

        if score > best_score:
            best_score = score
            best_match = cat['name']

    if best_match and best_score > 3:
        return best_match

    # === FALLBACK: создаём новую категорию ===
    if 'iphone' in item_text.lower():
        return f"{extract_base_name(item_text)}:"

    if ',' in item_text:
        new_header = item_text.split(',')[0].strip() + ':'
    else:
        words = item_text.split()
        new_header = ' '.join(words[:3]).strip() + ':'

    return normalize_name(new_header)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, state: FSMContext):
    # Проверка состояния и получение content (без изменений)
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                             text="⚠️ Сначала подтвердите предыдущую загрузку.",
                             reply_to_message_id=message.message_id,
                             message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
        return

    content = None
    if message.document:
        # ... проверка файла ...
        pass
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

    # Получаем существующие категории и умно определяем категорию для каждого товара
    existing_categories = await get_all_categories()

    for item in parsed_items:
        item['category'] = await determine_category_for_item(item['text'], existing_categories)

    await state.update_data(temp_items=parsed_items)
    await state.set_state(ArrivalConfirmState.waiting_for_confirm)

    preview = f"📥 Прибытие: {len(parsed_items)} товаров\n\n"
    for item in parsed_items[:12]:
        preview += f"• {item['text'][:65]} → **{item['category']}**\n"
    if len(parsed_items) > 12:
        preview += f"... и ещё {len(parsed_items)-12} товаров"

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
                category_name = item_data.get('category', 'Без категории')
                await get_or_create_category(category_name)

                await ItemRepository.add_item(
                    text=item_data['text'],
                    serial=item_data.get('serial'),
                    category_name=category_name
                )
                added += 1

            await callback.message.edit_text(f"✅ Успешно добавлено {added} товаров в ассортимент!")
        except Exception as e:
            logger.exception("Ошибка добавления прибытия")
            await callback.message.edit_text(f"❌ Ошибка: {e}")
    else:
        await callback.message.edit_text("❌ Загрузка отменена.")

    await state.clear()
    await callback.answer()
