import logging
import os

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.states import AssortmentConfirmState
from bot.repositories.item import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.sort import sort_assortment_to_categories

logger = logging.getLogger(__name__)
router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ASSORTMENT,
    (F.text | F.caption | F.document)
)
async def handle_assortment_upload(message: Message, state: FSMContext):
    logger.info(f"🔔 ПОЛУЧЕНО СООБЩЕЖЕНИЕ В АССОРТИМЕНТ: chat_id={message.chat.id}, thread_id={message.message_thread_id}")

    content = None

    if message.document:
        document = message.document
        if document.file_size and document.file_size > MAX_FILE_SIZE:
            await message.reply("❌ Файл слишком большой (макс. 10 МБ).")
            return
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await message.reply("⚠️ Отправьте текстовый файл .txt")
            return

        file_path = f"/tmp/{document.file_name}"
        await message.bot.download(document, destination=file_path)
        try:
            async with aiofiles.open(file_path, encoding='utf-8') as f:
                content = await f.read()
            if not content.strip():
                await message.reply("❌ Файл пуст.")
                return
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption
        if not content:
            await message.reply("⚠️ Отправьте текст или файл.")
            return
        content = content.strip()

    categories = sort_assortment_to_categories(content)

    if not categories:
        await message.reply(
            "❌ Не удалось распознать ни одной категории.\n\n"
            "Пример формата:\n"
            "---\n"
            "iPhone:\n"
            "---\n"
            "iPhone 15 (SN123456)\n"
            "iPhone 16 (SN789012)\n"
            "---"
        )
        return

    await state.update_data(temp_categories=categories)
    await state.set_state(AssortmentConfirmState.waiting_for_confirm)

    total_items = sum(len(cat.get('items', [])) for cat in categories)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="assort_confirm:yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="assort_confirm:no")
        ]
    ])

    await message.reply(
        f"📦 Найдено категорий: **{len(categories)}**\n"
        f"Всего позиций: **{total_items}**\n\n"
        "⚠️ Это **полностью заменит** текущий ассортимент.\n"
        "Подтверждаете?",
        reply_markup=keyboard
    )


@router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    categories = data.get("temp_categories", [])
    action = callback.data.split(":")[1]

    if action == "yes" and categories:
        try:
            logger.info(f"Начина
