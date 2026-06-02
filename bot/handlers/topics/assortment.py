# bot/handlers/topics/assortment.py
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
from bot.utils.helpers import send_and_clean
from bot.utils.sort import sort_assortment_to_categories

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ASSORTMENT,
    (F.text | F.caption | F.document)
)
async def handle_assortment_upload(message: Message, state: FSMContext):
    """Обработчик полной замены ассортимента через топик «Ассортимент»."""
    logger.info(f"📥 Получено сообщение в ассортимент от {message.from_user.id if message.from_user else 'unknown'}")

    # Защита от повторного подтверждения
    if await state.get_state() == AssortmentConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку ассортимента.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ASSORTMENT,
            delete_after=60
        )
        return

    content = None

    if message.document:
        document = message.document
        if document.file_size and document.file_size > MAX_FILE_SIZE:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="❌ Файл слишком большой (максимум 10 МБ).",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ASSORTMENT,
                delete_after=60
            )
            return

        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текстовый файл (.txt).",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ASSORTMENT,
                delete_after=60
            )
            return

        file_path = f"/tmp/{document.file_name}"
        await message.bot.download(document, destination=file_path)

        try:
            async with aiofiles.open(file_path, encoding='utf-8') as f:
                content = await f.read()
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption
        if content:
            content = content.strip()

        if not content:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текст или .txt файл с ассортиментом.",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ASSORTMENT,
                delete_after=60
            )
            return

    if not content:
        await send_and_clean(message.bot, message.chat.id, "❌ Получен пустой ассортимент.", delete_after=60)
        return

    # Парсинг
    categories = sort_assortment_to_categories(content)

    if not categories:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="❌ Не удалось распознать категории.\n\nПример формата:\n---\niPhone:\n---\niPhone 16 (SN123456)",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ASSORTMENT,
            delete_after=90
        )
        return

    total_items = sum(len(cat.get('items', [])) for cat in categories)

    logger.info(f"📦 Распознано: {len(categories)} категорий, {total_items} товаров")

    # Сохраняем в FSM
    await state.update_data(temp_categories=categories)
    await state.set_state(AssortmentConfirmState.waiting_for_confirm)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить замену", callback_data="assort_confirm:yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="assort_confirm:no")
    ]])

    await message.reply(
        f"📦 **Ассортимент готов к замене**\n\n"
        f"Категорий: **{len(categories)}**\n"
        f"Товаров: **{total_items}**\n\n"
        f"⚠️ Это **полностью заменит** текущий ассортимент в базе.\n"
        f"Подтверждаете?",
        reply_markup=keyboard
    )


@router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение замены ассортимента."""
    await callback.answer()
    data = await state.get_data()
    categories = data.get("temp_categories", [])

    if callback.data.split(":")[1] == "yes" and categories:
        try:
            logger.info(f"🔄 Полная замена ассортимента: {len(categories)} категорий")
            await ItemRepository.bulk_replace_assortment(categories)
            await AssortmentService.invalidate_cache()
            logger.info("✅ Ассортимент успешно заменён")
            await callback.message.edit_text("✅ Ассортимент успешно заменён.")
        except Exception as e:
            logger.exception("❌ Ошибка при замене ассортимента")
            await callback.message.edit_text(f"❌ Ошибка при сохранении: {e}")
    else:
        await callback.message.edit_text("❌ Замена ассортимента отменена.")

    await state.clear()
