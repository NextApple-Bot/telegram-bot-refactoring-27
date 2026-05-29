import logging
import os
import tempfile
from typing import Any

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import config
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import build_output_text

logger = logging.getLogger(__name__)

router = Router()


async def show_inventory(bot: Bot, chat_id: int) -> Message | None:
    """Показывает текущий ассортимент в виде документа."""
    try:
        categories = await AssortmentService.load_inventory()
        if not categories:
            return await send_and_clean(
                bot=bot,
                chat_id=chat_id,
                text="📭 Ассортимент пуст.",
                delete_after=60,
            )

        text = build_output_text(categories)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmp_path = f.name

        try:
            document = FSInputFile(tmp_path, filename="assortiment.txt")
            msg = await bot.send_document(
                chat_id,
                document,
                caption=f"📦 Текущий ассортимент (категорий: {len(categories)})",
            )
            return msg
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        logger.exception("Ошибка в show_inventory")
        await send_and_clean(
            bot=bot,
            chat_id=chat_id,
            text="❌ Ошибка при формировании ассортимента.",
            delete_after=60,
        )
        return None


async def show_help(bot: Bot, chat_id: int):
    """Выводит справку по командам."""
    help_text = """
👋 **Справка по командам бота**

**Основные команды:**
• /start — показать главное меню
• /inventory — выгрузить файл с ассортиментом
• /cancel — отменить текущее действие
• /help — эта справка

**Экспорт данных (только для админа):**
• /export_clients — выгрузить всех клиентов в CSV
• /export_purchases — выгрузить все покупки в CSV
• /export_full_report — полный отчёт (клиенты + покупки)
• /client_info <телефон/имя> — информация о клиенте

**Управление категориями (админ):**
• /show_categories — список категорий с ID
• /clean_empty — удалить все пустые категории
• /delete_category <ID> — удалить пустую категорию
• /merge_categories <from_id> <to_id> — объединить категории

**Управление данными (админ):**
• /reset_assortment — полностью очистить ассортимент
• /delete_client <ID> — удалить клиента и его покупки
• /delete_purchase <ID> — удалить конкретную покупку
• /undo — восстановить последний удалённый товар

**Кнопки в меню:**
• «Показать ассортимент» — аналог /inventory
• «Статистика» — продажи/брони за сегодня
• «Выгрузить ассортимент» — отправить в топик
• «Остатки» — остатки товаров (без брони и Б/У/NS)
• «Клиенты по месяцам» — скачать данные за месяц
"""
    await send_and_clean(
        bot=bot,
        chat_id=chat_id,
        text=help_text,
        parse_mode="Markdown",
        delete_after=60,
    )


async def cancel_action(bot: Bot, chat_id: int, state: FSMContext):
    """Отменяет текущее FSM-состояние."""
    try:
        await state.clear()
        await send_and_clean(
            bot=bot,
            chat_id=chat_id,
            text="✅ Действие отменено.",
            delete_after=60,
        )
    except Exception:
        logger.exception("Ошибка при отмене действия")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню (inline-кнопки)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Показать ассортимент", callback_data="menu:inventory"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
        ],
        [
            InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment"),
            InlineKeyboardButton(text="📦 Остатки", callback_data="menu:remains"),
        ],
        [
            InlineKeyboardButton(text="📅 Клиенты по месяцам", callback_data="menu:clients_by_month"),
            InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel"),
        ],
    ])


# ==================== Дополнительные полезные функции ====================

async def is_admin(user_id: int) -> bool:
    """Проверка администратора (используется в других хендлерах)."""
    return user_id in config.ADMIN_IDS


def create_back_button(text: str = "← Назад") -> InlineKeyboardMarkup:
    """Универсальная кнопка «Назад»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data="menu:cancel")]
    ])
