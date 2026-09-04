# bot/handlers/base.py

import logging
import os
import tempfile
from datetime import datetime

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.assortment import AssortmentService
from bot.utils.sort import build_output_text

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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 Ассортимент", callback_data="menu:inventory")],
            [InlineKeyboardButton(text="📋 Шаблоны продажи/брони", callback_data="menu:templates")],
            [InlineKeyboardButton(text="🎁 Акция", callback_data="menu:promo")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
            [InlineKeyboardButton(text="👥 Клиенты", callback_data="menu:clients")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
        ]
    )
    return keyboard


def get_promo_keyboard() -> InlineKeyboardMarkup:
    """Подменю акций."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Рассрочка 36 / 24 месяцев", callback_data="promo:installment")],
            [InlineKeyboardButton(text="♻️ Trade-IN", callback_data="promo:tradein")],
            [InlineKeyboardButton(text="♻️💳 Trade-IN + Рассрочка 36", callback_data="promo:tradein_installment")],
            [InlineKeyboardButton(text="🎂 В день рождения", callback_data="promo:birthday")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:cancel")],
        ]
    )
    return keyboard


async def show_help(bot: Bot, chat_id: int):
    """Показывает справку."""
    text = (
        "📖 <b>Справка по боту</b>\n\n"
        "Основные команды:\n"
        "/start — главное меню\n"
        "/inventory — показать ассортимент (файл)\n"
        "/templates — шаблоны продажи и брони\n"
        "/sale_template — шаблон продажи\n"
        "/booking_template — шаблон брони\n"
        "/cancel — отменить текущее действие\n"
        "/help — эта справка\n\n"
        "Административные команды доступны только админам."
    )
    await bot.send_message(chat_id, text, parse_mode="HTML")


async def show_inventory(bot: Bot, chat_id: int):
    """
    Отправляет текущий ассортимент файлом .txt
    в том же формате, в котором его загружают.
    """
    try:
        categories = await AssortmentService.load_inventory()
        if not categories:
            await bot.send_message(chat_id, "📭 Ассортимент пуст.")
            return None

        normalized = []
        for cat in categories:
            items = cat.get("items", [])
            item_strings = []
            for it in items:
                if isinstance(it, dict):
                    item_strings.append(it.get("text", ""))
                else:
                    item_strings.append(str(it))
            normalized.append(
                {
                    "header": cat.get("header") or cat.get("name") or "Общее",
                    "items": item_strings,
                }
            )

        text = build_output_text(normalized)
        total_items = sum(len(c["items"]) for c in normalized)
        today = datetime.now().strftime("%d.%m.%Y")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmp_path = f.name

        try:
            document = FSInputFile(tmp_path, filename=f"assortiment_{today}.txt")
            msg = await bot.send_document(
                chat_id=chat_id,
                document=document,
                caption=(
                    f"📦 Текущий ассортимент\n"
                    f"Категорий: {len(normalized)}\n"
                    f"Товаров: {total_items}"
                ),
            )
            return msg
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception:
        logger.exception("Ошибка при показе ассортимента")
        await bot.send_message(chat_id, "❌ Не удалось загрузить ассортимент.")
        return None
