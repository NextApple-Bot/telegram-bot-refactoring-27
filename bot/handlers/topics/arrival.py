import logging
import os
import re

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.states import ArrivalConfirmState
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)
router = Router()


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
        if base.startswith(cat_name) and len(cat_name) > best_len:
            best_len = len(cat_name)
            best_match = cat['header']
        elif cat_name in base and len(cat_name) > best_len:
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
    # ... (логика парсинга и определения категории остаётся как в предыдущей версии)
    # Для brevity я опустил часть, но она такая же, как в последней отправленной версии
    pass   # ← замени на полный handle_arrival из предыдущего сообщения


@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat_to_items = data.get("cat_to_items", {})
    action = callback.data.split(":")[1]

    if action != "yes":
        await callback.message.edit_text("❌ Отменено.")
        await state.clear()
        await callback.answer()
        return

    total_added = 0
    failed = []

    for cat_name, items in cat_to_items.items():
        for text, serial in items:
            try:
                await ItemRepository.add_item(
                    text=text,
                    serial=serial,
                    category_name=cat_name
                )
                total_added += 1
            except Exception as e:
                logger.error(f"Не удалось добавить товар: {text} | {e}")
                failed.append(text)

    try:
        await AssortmentService.invalidate_cache()
    except Exception:
        pass

    if total_added > 0 and not failed:
        await callback.message.edit_text(f"✅ Успешно добавлено {total_added} товаров!")
    elif total_added > 0:
        msg = f"✅ Добавлено: {total_added}\n❌ Не удалось добавить:\n"
        for item in failed[:6]:
            msg += f"• {item}\n"
        await callback.message.edit_text(msg)
    else:
        await callback.message.edit_text("❌ Не удалось добавить товары.")

    await state.clear()
    await callback.answer()
