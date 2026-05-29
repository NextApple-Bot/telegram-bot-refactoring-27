import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.service_commands import (
    delete_category_if_empty,
    delete_client_by_id,
    delete_purchase_by_id,
    export_clients_csv,
    export_full_report_csv,
    export_purchases_csv,
    find_empty_categories,
    fix_sales_unique,
    get_client_info_text,
    list_categories_text,
    merge_categories,
    set_webhook_manually,
    undo_last_deletion,
)
from bot.utils.helpers import send_and_clean
from bot.utils.markdown import escape_markdown_v1

from .base import cancel_action, get_main_menu_keyboard, show_help, show_inventory

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Проверка администратора (используем актуальный config)."""
    return user_id in config.ADMIN_IDS


@router.message(Command("start"))
async def cmd_start(message: Message):
    try:
        keyboard = get_main_menu_keyboard()
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60,
        )
    except Exception:
        logger.exception("Ошибка в /start")


@router.message(Command("inventory"))
async def cmd_inventory(message: Message):
    await show_inventory(message.bot, message.chat.id)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state):
    await cancel_action(message.bot, message.chat.id, state)
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="Главное меню:",
        reply_markup=get_main_menu_keyboard(),
        message_thread_id=message.message_thread_id,
        delete_after=60,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await show_help(message.bot, message.chat.id)


# ==================== Экспорт данных ====================
@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        file_path = await export_clients_csv()
        await message.answer_document(
            FSInputFile(file_path, filename="clients.csv"),
            caption="📁 Экспорт клиентов"
        )
    except Exception:
        logger.exception("Ошибка экспорта клиентов")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка экспорта")


@router.message(Command("export_purchases"))
async def cmd_export_purchases(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        file_path = await export_purchases_csv()
        await message.answer_document(
            FSInputFile(file_path, filename="purchases.csv"),
            caption="📁 Экспорт покупок"
        )
    except Exception:
        logger.exception("Ошибка экспорта покупок")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка экспорта")


@router.message(Command("client_info"))
async def cmd_client_info(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return

    args = message.text.replace("/client_info", "").strip()
    if not args:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Укажите телефон или имя клиента")
        return
    try:
        text = await get_client_info_text(args)
        if text is None:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Клиент не найден")
            return
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=text,
            parse_mode="Markdown"
        )
    except Exception:
        logger.exception("Ошибка получения информации о клиенте")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("export_full_report"))
async def cmd_export_full_report(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        file_path = await export_full_report_csv()
        await message.answer_document(
            FSInputFile(file_path, filename="full_report.csv"),
            caption="📁 Полный отчёт"
        )
    except Exception:
        logger.exception("Ошибка экспорта полного отчёта")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка экспорта")


# ==================== Управление категориями ====================
@router.message(Command("show_categories"))
async def cmd_show_categories(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        text = await list_categories_text()
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=text,
            parse_mode="Markdown"
        )
    except Exception:
        logger.exception("Ошибка списка категорий")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("clean_empty"))
async def cmd_clean_empty(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        empty = await find_empty_categories()
        if not empty:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="✅ Пустых категорий нет.")
            return

        categories_list = "\n".join(
            [f"• {escape_markdown_v1(r['name'])} (ID {r['id']})" for r in empty]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить все", callback_data="clean_empty:confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Найдены пустые категории:\n{categories_list}\n\nУдалить их?",
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Ошибка поиска пустых категорий")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("delete_category"))
async def cmd_delete_category(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 2:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /delete_category <ID>")
        return
    try:
        cat_id = int(args[1])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должен быть числом")
        return

    try:
        can_delete, reason = await delete_category_if_empty(cat_id)
        if not can_delete:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=reason)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_cat:{cat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Точно удалить категорию {reason}?",
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Ошибка подготовки удаления категории")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("merge_categories"))
async def cmd_merge_categories(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 3:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                             text="❌ Используйте: /merge_categories <from_id> <to_id>")
        return
    try:
        from_id = int(args[1])
        to_id = int(args[2])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должны быть числами")
        return

    if from_id == to_id:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должны быть разными")
        return

    try:
        can_merge, msg_text = await merge_categories(from_id, to_id)
        if not can_merge:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=msg_text)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, перенести и удалить", callback_data=f"merge:{from_id}:{to_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=msg_text,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Ошибка подготовки слияния категорий")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("reset_assortment"))
async def cmd_reset_assortment(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, УДАЛИТЬ ВСЁ", callback_data="reset_assortment:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="⚠️ **ВНИМАНИЕ!** Эта команда **полностью удалит** все товары и категории из ассортимента.\n"
             "Данные о клиентах, покупках, статистике и бронях сохранятся.\n\nВы уверены?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ==================== Удаление по ID ====================
@router.message(Command("delete_client"))
async def cmd_delete_client(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 2:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /delete_client <ID>")
        return
    try:
        client_id = int(args[1])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должен быть числом")
        return

    try:
        can_delete, warning = await delete_client_by_id(client_id)
        if not can_delete:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=warning)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_client:{client_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=warning,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Ошибка подготовки удаления клиента")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("delete_purchase"))
async def cmd_delete_purchase(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 2:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /delete_purchase <ID>")
        return
    try:
        purchase_id = int(args[1])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должен быть числом")
        return

    try:
        can_delete, warning = await delete_purchase_by_id(purchase_id)
        if not can_delete:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=warning)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_purchase:{purchase_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=warning,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception("Ошибка подготовки удаления покупки")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


# ==================== Остальные команды ====================
@router.message(Command("undo"))
async def cmd_undo(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        text = await undo_last_deletion()
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=text)
    except Exception:
        logger.exception("Ошибка восстановления")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    response = f"Chat ID: `{chat_id}`\n"
    if thread_id:
        response += f"Thread ID: `{thread_id}`"
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text=response,
        parse_mode="Markdown"
    )


@router.message(Command("fix_sales_unique"))
async def cmd_fix_sales_unique(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        result_msg = await fix_sales_unique()
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=result_msg)
    except Exception:
        logger.exception("Ошибка fix_sales_unique")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")


@router.message(Command("set_webhook"))
async def cmd_set_webhook(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён")
        return
    try:
        result_msg = await set_webhook_manually()
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=result_msg,
            parse_mode="Markdown"
        )
    except Exception:
        logger.exception("Ошибка ручной установки вебхука")
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Ошибка")
