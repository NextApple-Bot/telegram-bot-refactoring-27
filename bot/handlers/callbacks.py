import csv
import json
import logging
import os
import tempfile
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from cachetools import TTLCache
from sqlalchemy import select

from bot.config import config
from bot.db import get_async_session_factory
from bot.models import Category, Item
from bot.repositories import ClientRepository, StatsRepository
from bot.utils.helpers import send_and_clean
from bot.utils.sort import detect_sim_type, get_full_model_name

from .base import get_main_menu_keyboard, get_promo_keyboard, show_help, show_inventory
from .service_commands import delete_category_by_id, merge_categories_action, reset_assortment_action
from .templates_cmd import templates_keyboard
from .topics.common import export_assortment_to_topic

router = Router()
logger = logging.getLogger(__name__)

# Кэши для предотвращения дублирования сообщений
last_stats_message = TTLCache(maxsize=1000, ttl=3600)
last_inventory_message = TTLCache(maxsize=1000, ttl=3600)
last_remains_message = TTLCache(maxsize=1000, ttl=3600)
last_clients_month_message = TTLCache(maxsize=1000, ttl=3600)


async def safe_delete(message):
    """Безопасное удаление сообщения."""
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")


def is_admin(user_id: int) -> bool:
    """Проверка администратора."""
    return user_id in config.ADMIN_IDS


@router.callback_query(F.data == "menu:inventory")
async def process_inventory(callback: CallbackQuery):
    await callback.answer("⏳ Загружаю ассортимент...")
    chat_id = callback.message.chat.id

    if chat_id in last_inventory_message:
        try:
            await callback.bot.delete_message(chat_id, last_inventory_message[chat_id])
        except Exception:
            pass

    msg = await show_inventory(callback.bot, chat_id)
    if msg:
        last_inventory_message[chat_id] = msg.message_id

    await safe_delete(callback.message)
    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=chat_id,
        text="Выберите действие:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )


@router.callback_query(F.data == "menu:templates")
async def process_templates_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Выберите шаблон для копирования или отправки в топик:",
        reply_markup=templates_keyboard(),
    )


@router.callback_query(F.data == "menu:promo")
async def process_promo_menu(callback: CallbackQuery):
    await callback.answer()
    await safe_delete(callback.message)
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="🎁 <b>Акции</b>\n\nВыберите интересующую акцию:",
        reply_markup=get_promo_keyboard(),
        parse_mode="HTML",
        message_thread_id=callback.message.message_thread_id,
        delete_after=120,
    )


@router.callback_query(F.data == "promo:installment")
async def process_promo_installment(callback: CallbackQuery):
    await callback.answer()
    text = (
        "💳 <b>Рассрочка 36 или 24 месяцев</b>\n\n"
        "<b>36 Месяцев</b>\n"
        "— полный комплект аксессуаров:\n"
        "• Чехол\n"
        "• Стекло\n"
        "• Блок Питания\n"
        "+ повербанк Xiaomi или колонка Яндекс Алиса.\n\n"
        "<b>24 Месяца</b>\n"
        "повербанк Xiaomi в подарок.\n\n"
        "<i>Чем больше срок – тем больше подарок.</i>"
    )
    await safe_delete(callback.message)
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_promo_keyboard(),
        message_thread_id=callback.message.message_thread_id,
        delete_after=180,
    )


@router.callback_query(F.data == "promo:tradein")
async def process_promo_tradein(callback: CallbackQuery):
    await callback.answer()
    text = (
        "♻️ <b>Trade-IN</b>\n\n"
        "В подарок вы получаете:\n"
        "✅ Защитное стекло Remax\n"
        "✅ Чехол с MagSafe (цвет на ваш выбор)\n"
        "✅ Оригинальный блок питания Apple 20 Вт\n"
        "✅ Ультра-тонкий повербанк Xiaomi\n\n"
        "<b>Дополнительная скидка на новое устройство:</b>\n"
        "• до 50 000 ₽ — скидка 1 000 ₽\n"
        "• до 100 000 ₽ — скидка 2 000 ₽\n"
        "• выше 100 000 ₽ — скидка 3 000 ₽"
    )
    await safe_delete(callback.message)
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_promo_keyboard(),
        message_thread_id=callback.message.message_thread_id,
        delete_after=180,
    )


@router.callback_query(F.data == "promo:tradein_installment")
async def process_promo_tradein_installment(callback: CallbackQuery):
    await callback.answer()
    text = (
        "♻️💳 <b>Trade-IN + Рассрочка 36 Месяцев</b>\n\n"
        "Сдаёте старый iPhone по Trade-in и оформляете новый в рассрочку на Халву 36 месяцев?\n\n"
        "Получаете:\n"
        "♻️ скидку за старый iPhone по Trade-IN\n"
        "✅ Защитное стекло Remax\n"
        "✅ Чехол с MagSafe (цвет на ваш выбор)\n"
        "✅ Оригинальный блок питания Apple 20 Вт\n"
        "✅ Ультра-тонкий повербанк Xiaomi\n\n"
        "🎁 колонку Яндекс Алиса\n\n"
        "<b>Дополнительная скидка на новое устройство:</b>\n"
        "• до 50 000 ₽ — скидка 1 000 ₽\n"
        "• до 100 000 ₽ — скидка 2 000 ₽\n"
        "• выше 100 000 ₽ — скидка 3 000 ₽"
    )
    await safe_delete(callback.message)
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_promo_keyboard(),
        message_thread_id=callback.message.message_thread_id,
        delete_after=180,
    )


@router.callback_query(F.data == "promo:birthday")
async def process_promo_birthday(callback: CallbackQuery):
    await callback.answer()
    text = (
        "🎂 <b>В день рождения</b>\n\n"
        "Скидка — до <b>5 000 ₽</b>, в зависимости от выбора устройства."
    )
    await safe_delete(callback.message)
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=text,
        parse_mode="HTML",
        reply_markup=get_promo_keyboard(),
        message_thread_id=callback.message.message_thread_id,
        delete_after=180,
    )


@router.callback_query(F.data == "menu:stats")
async def process_stats(callback: CallbackQuery):
    await callback.answer("⏳ Загружаю статистику...")
    chat_id = callback.message.chat.id

    if chat_id in last_stats_message:
        try:
            await callback.bot.delete_message(chat_id, last_stats_message[chat_id])
        except Exception:
            pass

    stats = await StatsRepository.get_today_stats()

    stats_text = (
        f"📊 Статистика на {stats['date']}\n\n"
        f"Продажи: {stats['sales_count']}\n"
        f"Предзаказы: {stats['preorders_count']}\n"
        f"Брони: {stats['bookings_count']}\n\n"
        f"💰 Суммы продаж:\n"
        f"Наличные: {stats['sales']['cash']:.0f} ₽\n"
        f"Терминал: {stats['sales']['terminal']:.0f} ₽\n"
        f"QR-код: {stats['sales']['qr']:.0f} ₽\n"
        f"Перевод: {stats['sales']['transfer']:.0f} ₽\n"
        f"По счёту: {stats['sales']['invoice']:.0f} ₽\n"
        f"Рассрочка: {stats['sales']['installment']:.0f} ₽\n\n"
        f"💸 Предзаказы:\n"
        f"Наличные: {stats['preorders']['cash']:.0f} ₽\n"
        f"Терминал: {stats['preorders']['terminal']:.0f} ₽\n"
        f"QR-код: {stats['preorders']['qr']:.0f} ₽\n"
        f"Перевод: {stats['preorders']['transfer']:.0f} ₽\n"
        f"По счёту: {stats['preorders']['invoice']:.0f} ₽\n"
        f"Рассрочка: {stats['preorders']['installment']:.0f} ₽\n\n"
        f"🔖 Брони: {stats['bookings_total']:.0f} ₽"
    )

    await safe_delete(callback.message)
    msg = await send_and_clean(
        bot=callback.bot,
        chat_id=chat_id,
        text=stats_text,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )
    last_stats_message[chat_id] = msg.message_id

    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=chat_id,
        text="Выберите действие:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )


@router.callback_query(F.data == "menu:help")
async def process_help(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id
    await show_help(callback.bot, chat_id)
    await safe_delete(callback.message)
    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=chat_id,
        text="Выберите действие:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )


@router.callback_query(F.data == "menu:clients")
async def process_clients(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Экспорт клиентов (CSV)", callback_data="menu:export_clients_hint")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:cancel")],
    ])
    await safe_delete(callback.message)
    await send_and_clean(
        bot=callback.bot,
        chat_id=chat_id,
        text=(
            "👥 <b>Клиенты</b>\n\n"
            "Для экспорта используйте команды:\n"
            "/export_clients — все клиенты\n"
            "/client_info <телефон или имя> — карточка клиента\n"
            "/export_purchases — покупки\n"
            "/export_full_report — полный отчёт"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
        message_thread_id=callback.message.message_thread_id,
        delete_after=120,
    )


@router.callback_query(F.data == "menu:export_clients_hint")
async def process_export_clients_hint(callback: CallbackQuery):
    await callback.answer("Используйте команду /export_clients", show_alert=True)


@router.callback_query(F.data == "menu:export_assortment")
async def process_export_assortment(callback: CallbackQuery):
    await callback.answer("⏳ Выгружаю ассортимент...")
    await export_assortment_to_topic(callback.bot, callback.from_user.id)
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.from_user.id,
        text="✅ Ассортимент выгружен в топик.",
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )


@router.callback_query(F.data == "menu:clear")
async def process_clear(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, УДАЛИТЬ ВСЁ", callback_data="reset_assortment:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="⚠️ **ВНИМАНИЕ!** Эта команда **полностью удалит** все товары и категории.\n"
             "Данные о клиентах, покупках и статистике сохранятся.\n\nВы уверены?",
        reply_markup=keyboard,
        parse_mode='Markdown',
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )


@router.callback_query(F.data == "menu:remains")
async def process_remains(callback: CallbackQuery):
    await callback.answer("⏳ Формирую отчёт по остаткам...")
    chat_id = callback.message.chat.id

    if chat_id in last_remains_message:
        try:
            await callback.bot.delete_message(chat_id, last_remains_message[chat_id])
        except Exception:
            pass

    async with get_async_session_factory()() as session:
        result = await session.execute(
            select(Item.text)
            .join(Category, Item.category_id == Category.id)
            .where(~Item.is_booked, ~Category.name.in_(['Б/У:', 'Б/У', 'NS:', 'NS']))
        )
        rows = result.all()

    if not rows:
        await safe_delete(callback.message)
        await send_and_clean(
            bot=callback.bot,
            chat_id=chat_id,
            text="📭 Нет товаров в наличии.",
            message_thread_id=callback.message.message_thread_id,
            delete_after=60,
        )
        keyboard = get_main_menu_keyboard()
        await send_and_clean(
            bot=callback.bot,
            chat_id=chat_id,
            text="Выберите действие:",
            reply_markup=keyboard,
            message_thread_id=callback.message.message_thread_id,
            delete_after=60,
        )
        return

    groups = {}
    for row in rows:
        text = row[0]
        full_name = get_full_model_name(text)
        sim = detect_sim_type(text)
        key = (full_name, sim)
        groups[key] = groups.get(key, 0) + 1

    today = datetime.now().strftime("%d.%m.%y")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['Модель', 'Тип SIM', 'Количество'])
        for (full_name, sim), count in sorted(groups.items()):
            writer.writerow([full_name, sim if sim != 'other' else '', count])
        tmp_path = tmp.name

    await safe_delete(callback.message)
    sent = await callback.message.answer_document(
        FSInputFile(tmp_path, filename=f"remains_{today}.csv"),
        caption=f"📦 Остатки на {today}"
    )
    last_remains_message[chat_id] = sent.message_id
    os.unlink(tmp_path)

    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=chat_id,
        text="Выберите действие:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )


@router.callback_query(F.data.startswith("reset_assortment:confirm"))
async def process_reset_assortment_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await reset_assortment_action(callback)


@router.callback_query(F.data.startswith("delete_cat:"))
async def process_delete_category(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        cat_id = int(callback.data.split(":")[1])
        await delete_category_by_id(callback, cat_id)
    except Exception:
        logger.exception("Ошибка удаления категории")
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


@router.callback_query(F.data.startswith("merge:"))
async def process_merge_categories(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        _, from_id, to_id = callback.data.split(":")
        await merge_categories_action(callback, int(from_id), int(to_id))
    except Exception:
        logger.exception("Ошибка слияния категорий")
        await callback.answer("❌ Ошибка при слиянии", show_alert=True)


@router.callback_query(F.data.startswith("month:"))
async def process_month_selection(callback: CallbackQuery):
    await callback.answer()
    month = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    if chat_id in last_clients_month_message:
        try:
            await callback.bot.delete_message(chat_id, last_clients_month_message[chat_id])
        except Exception:
            pass

    await callback.message.edit_text(f"⏳ Формирую отчёт за {month}...")

    try:
        rows = await ClientRepository.get_clients_data_for_month(month)
        if not rows:
            await safe_delete(callback.message)
            await send_and_clean(
                bot=callback.bot,
                chat_id=chat_id,
                text="📭 Нет данных за этот месяц.",
                message_thread_id=callback.message.message_thread_id,
                delete_after=60,
            )
            keyboard = get_main_menu_keyboard()
            await send_and_clean(
                bot=callback.bot,
                chat_id=chat_id,
                text="Выберите действие:",
                reply_markup=keyboard,
                message_thread_id=callback.message.message_thread_id,
                delete_after=60,
            )
            return

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            writer = csv.writer(tmp)
            writer.writerow([
                'ID клиента', 'ФИО', 'Телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник',
                'Дата регистрации клиента', 'ID покупки', 'Дата покупки', 'Товары', 'Сумма',
                'Способ оплаты (JSON)', 'Тип покупки'
            ])
            for row in rows:
                items_text = ''
                if row.get('items_json'):
                    try:
                        items = json.loads(row['items_json'])
                        items_text = '; '.join([f"{it.get('item_text', '')[:50]} ({it.get('price', '')}₽)" for it in items])
                    except Exception:
                        items_text = str(row['items_json'])
                client_created = row['client_created_at'].strftime("%d.%m.%y") if row.get('client_created_at') else ''
                purchase_created = row['purchase_created_at'].strftime("%d.%m.%y") if row.get('purchase_created_at') else ''
                writer.writerow([
                    row.get('client_id'), row.get('full_name'), row.get('phone'), row.get('phones'),
                    row.get('telegram_username'), row.get('social_network'), row.get('referral_source'),
                    client_created, row.get('purchase_id'), purchase_created,
                    items_text, row.get('total_amount'), row.get('payment_details'), row.get('purchase_type')
                ])
            tmp_path = tmp.name

        await safe_delete(callback.message)
        sent = await callback.message.answer_document(
            FSInputFile(tmp_path, filename=f"clients_{month}.csv"),
            caption=f"📁 Данные клиентов за {month}"
        )
        last_clients_month_message[chat_id] = sent.message_id
        os.unlink(tmp_path)

        keyboard = get_main_menu_keyboard()
        await send_and_clean(
            bot=callback.bot,
            chat_id=chat_id,
            text="Выберите действие:",
            reply_markup=keyboard,
            message_thread_id=callback.message.message_thread_id,
            delete_after=60,
        )

    except Exception:
        logger.exception(f"Ошибка при формировании отчёта за {month}")
        await safe_delete(callback.message)
        await send_and_clean(
            bot=callback.bot,
            chat_id=chat_id,
            text="❌ Произошла ошибка при формировании отчёта.",
            message_thread_id=callback.message.message_thread_id,
            delete_after=60,
        )


@router.callback_query(F.data == "menu:cancel")
async def process_cancel(callback: CallbackQuery):
    await callback.answer("Отменено")
    await safe_delete(callback.message)
    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="Главное меню:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )
