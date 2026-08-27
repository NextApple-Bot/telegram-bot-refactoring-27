"""
Команды и кнопки: шаблон продажи / брони для копирования в топик.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import config
from bot.utils.helpers import send_and_clean
from bot.utils.sale_templates import (
    get_booking_template,
    get_booking_template_help,
    get_sale_template,
    get_sale_template_help,
    get_sale_template_with_accessories,
)

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def templates_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧾 Продажа (просто)", callback_data="tpl:sale"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧾 Продажа + аксессуары/UDS",
                    callback_data="tpl:sale_acc",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📌 Бронь", callback_data="tpl:booking"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 В топик продаж", callback_data="tpl:send_sale_topic"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 В топик брони", callback_data="tpl:send_booking_topic"
                )
            ],
        ]
    )


@router.message(Command("sale_template", "template_sale", "шаблон_продажи"))
async def cmd_sale_template(message: Message):
    await message.answer(
        get_sale_template_help(),
        parse_mode="HTML",
        reply_markup=templates_keyboard(),
    )
    await message.answer(f"<pre>{get_sale_template()}</pre>", parse_mode="HTML")


@router.message(Command("booking_template", "template_booking", "шаблон_брони"))
async def cmd_booking_template(message: Message):
    await message.answer(
        get_booking_template_help(),
        parse_mode="HTML",
        reply_markup=templates_keyboard(),
    )
    await message.answer(f"<pre>{get_booking_template()}</pre>", parse_mode="HTML")


@router.message(Command("templates", "шаблоны"))
async def cmd_templates(message: Message):
    await message.answer(
        "Выберите шаблон для копирования:",
        reply_markup=templates_keyboard(),
    )


@router.callback_query(F.data.startswith("tpl:"))
async def on_template_callback(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception:
        pass

    action = (callback.data or "").split(":", 1)[-1]
    chat_id = callback.message.chat.id if callback.message else None
    if not chat_id:
        return

    try:
        if action == "sale":
            await callback.message.answer(
                get_sale_template_help(), parse_mode="HTML"
            )
            await callback.message.answer(
                f"<pre>{get_sale_template()}</pre>", parse_mode="HTML"
            )
        elif action == "sale_acc":
            await callback.message.answer(
                get_sale_template_help(), parse_mode="HTML"
            )
            await callback.message.answer(
                f"<pre>{get_sale_template_with_accessories()}</pre>",
                parse_mode="HTML",
            )
        elif action == "booking":
            await callback.message.answer(
                get_booking_template_help(), parse_mode="HTML"
            )
            await callback.message.answer(
                f"<pre>{get_booking_template()}</pre>", parse_mode="HTML"
            )
        elif action == "send_sale_topic":
            if not _is_admin(callback.from_user.id):
                await callback.answer("Только для админов", show_alert=True)
                return
            await callback.bot.send_message(
                chat_id=config.MAIN_GROUP_ID,
                text=get_sale_template(),
                message_thread_id=config.THREAD_SALES,
            )
            await send_and_clean(
                bot=callback.bot,
                chat_id=chat_id,
                text="✅ Шаблон продажи отправлен в топик Продажи",
                delete_after=30,
            )
        elif action == "send_booking_topic":
            if not _is_admin(callback.from_user.id):
                await callback.answer("Только для админов", show_alert=True)
                return
            await callback.bot.send_message(
                chat_id=config.MAIN_GROUP_ID,
                text=get_booking_template(),
                message_thread_id=config.THREAD_PREORDER,
            )
            await send_and_clean(
                bot=callback.bot,
                chat_id=chat_id,
                text="✅ Шаблон брони отправлен в топик Предзаказ",
                delete_after=30,
            )
    except Exception:
        logger.exception("Ошибка отправки шаблона action=%s", action)
        try:
            await callback.message.answer("❌ Не удалось отправить шаблон")
        except Exception:
            pass
