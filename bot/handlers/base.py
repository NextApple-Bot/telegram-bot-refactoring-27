# bot/handlers/base.py

import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.assortment import AssortmentService

logger = logging.getLogger(__name__)


async def cancel_action(bot: Bot, chat_id: int, state: FSMContext):
    """Отменяет текущее состояние FSM."""
    current_state = await state.get_state()
    if current_state is None:
        await bot.send_message(chat_id, "Нет активного действия для отмены.")
        return

    await state.clear()
    await bot.send_message(chat_id, "✅ Действие отменено.")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Возвращает главное меню."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Ассортимент", callback_data="menu:inventory")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton(text="👥 Клиенты", callback_data="menu:clients")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])
    return keyboard


async def show_help(bot: Bot, chat_id: int):
    """Показывает справку."""
    text = (
        "📖 <b>Справка по боту</b>\n\n"
        "Основные команды:\n"
        "/start — главное меню\n"
        "/inventory — показать ассортимент\n"
        "/cancel — отменить текущее действие\n"
        "/help — эта справка\n\n"
        "Административные команды доступны только админам."
    )
    await bot.send_message(chat_id, text, parse_mode="HTML")


async def show_inventory(bot: Bot, chat_id: int):
    """Показывает текущий ассортимент (упрощённая версия)."""
    try:
        categories = await AssortmentService.load_inventory()
        if not categories:
            await bot.send_message(chat_id, "📭 Ассортимент пуст.")
            return None

        total_items = sum(len(cat.get("items", [])) for cat in categories)
        text = f"📦 **Текущий ассортимент**\n\n"
        text += f"Категорий: **{len(categories)}**\n"
        text += f"Всего товаров: **{total_items}**\n\n"

        # Краткий список категорий с количеством товаров
        for cat in categories[:30]:  # ограничение, чтобы не превысить лимит Telegram
            name = cat.get("header", "Без названия")
            count = len(cat.get("items", []))
            text += f"• {name}: {count}\n"

        if len(categories) > 30:
            text += f"\n… и ещё {len(categories) - 30} категорий"

        msg = await bot.send_message(chat_id, text, parse_mode="Markdown")
        return msg

    except Exception as e:
        logger.exception("Ошибка при показе ассортимента")
        await bot.send_message(chat_id, "❌ Не удалось загрузить ассортимент.")
        return None
