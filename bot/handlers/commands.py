# bot/handlers/base.py

import logging
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
        [InlineKeyboardButton(text="📦 Ассортимент", callback_data="menu:assortment")],
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
    """Показывает текущий ассортимент (заглушка)."""
    await bot.send_message(chat_id, "📦 Функция просмотра ассортимента пока в разработке.")
