from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.utils.helpers import send_and_clean

router = Router()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота (как было раньше)."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Показать ассортимент", callback_data="menu:inventory"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
        ],
        [
            InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment"),
            InlineKeyboardButton(text="📦 Остатки", callback_data="menu:remains"),
        ],
        [
            InlineKeyboardButton(text="👥 Клиенты по месяцам", callback_data="menu:clients_month"),
            InlineKeyboardButton(text="🗑 Очистить ассортимент", callback_data="menu:clear"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel"),
        ],
    ])
    return keyboard


@router.message(CommandStart())
async def cmd_start(message: Message):
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="👋 Добро пожаловать! Используйте кнопки ниже для управления.",
        reply_markup=get_main_menu_keyboard(),
        message_thread_id=message.message_thread_id,
        delete_after=120,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="📌 Доступные команды:\n"
             "/start — главное меню\n"
             "/inventory — показать ассортимент\n"
             "/help — помощь",
        message_thread_id=message.message_thread_id,
        delete_after=60,
    )