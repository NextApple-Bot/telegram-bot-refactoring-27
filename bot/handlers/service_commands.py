import csv
import logging
import tempfile
from typing import Tuple

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, func, select, update

from bot.config import config
from bot.db import get_async_session_factory
from bot.models import Category, Client, Item, Purchase
from bot.repositories.client import ClientRepository
from bot.repositories.item import ItemRepository
from bot.utils.helpers import send_and_clean
from bot.utils.markdown import escape_markdown_v1

logger = logging.getLogger(__name__)


# ====================== УДАЛЕНИЕ КАТЕГОРИИ ======================
async def delete_category_if_empty(cat_id: int) -> Tuple[bool, str]:
    async with get_async_session_factory()() as session:
        cat = await session.get(Category, cat_id)
        if not cat:
            return False, "❌ Категория не найдена"
        items_count = await session.scalar(
            select(func.count()).select_from(Item).where(Item.category_id == cat_id)
        )
        if items_count > 0:
            return False, f"❌ Категория «{cat.name}» не пустая ({items_count} товаров)"
        return True, f"«{cat.name}» (ID {cat_id})"


async def delete_category_by_id(callback: CallbackQuery, cat_id: int):
    try:
        async with get_async_session_factory()() as session:
            cat = await session.get(Category, cat_id)
            if not cat:
                await callback.answer("Категория не найдена", show_alert=True)
                return
            await session.delete(cat)
            await session.commit()
            await callback.answer(f"✅ Категория «{cat.name}» удалена", show_alert=True)
            await send_and_clean(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text=f"✅ Категория **{escape_markdown_v1(cat.name)}** успешно удалена.",
                parse_mode="Markdown",
                delete_after=60,
            )
    except Exception:
        logger.exception("Ошибка удаления категории")
        await callback.answer("❌ Ошибка при удалении категории", show_alert=True)


# ====================== СЛИЯНИЕ КАТЕГОРИЙ ======================
async def merge_categories(from_id: int, to_id: int) -> Tuple[bool, str]:
    if from_id == to_id:
        return False, "❌ ID категорий совпадают"
    async with get_async_session_factory()() as session:
        from_cat = await session.get(Category, from_id)
        to_cat = await session.get(Category, to_id)
        if not from_cat or not to_cat:
            return False, "❌ Одна из категорий не найдена"
        items_count = await session.scalar(
            select(func.count()).select_from(Item).where(Item.category_id == from_id)
        )
        return True, (
            f"Перенести **{items_count}** товаров из «{from_cat.name}» в «{to_cat.name}»?\n"
            f"После этого категория {from_cat.name} будет удалена."
        )


async def merge_categories_action(callback: CallbackQuery, from_id: int, to_id: int):
    try:
        async with get_async_session_factory()() as session:
            await session.execute(
                update(Item)
                .where(Item.category_id == from_id)
                .values(category_id=to_id)
            )
            from_cat = await session.get(Category, from_id)
            await session.delete(from_cat)
            await session.commit()
        await callback.answer("✅ Категории объединены", show_alert=True)
        await send_and_clean(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text="✅ Категории успешно объединены.",
            delete_after=60,
        )
    except Exception:
        logger.exception("Ошибка слияния категорий")
        await callback.answer("❌ Ошибка при слиянии", show_alert=True)


# ====================== ПОЛНЫЙ СБРОС АССОРТИМЕНТА ======================
async def reset_assortment_action(callback: CallbackQuery):
    if not (callback.from_user.id in config.ADMIN_IDS):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    try:
        async with get_async_session_factory()() as session:
            await session.execute(delete(Item))
            await session.execute(delete(Category))
            await session.commit()
        await callback.answer("✅ Ассортимент полностью очищен", show_alert=True)
        await send_and_clean(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text="✅ **Ассортимент полностью очищен.**\nТовары и категории удалены.",
            parse_mode="Markdown",
            delete_after=60,
        )
    except Exception:
        logger.exception("Ошибка полного сброса ассортимента")
        await callback.answer("❌ Ошибка при очистке", show_alert=True)


# ====================== УДАЛЕНИЕ КЛИЕНТА ======================
async def delete_client_by_id(client_id: int) -> Tuple[bool, str]:
    async with get_async_session_factory()() as session:
        client = await session.get(Client, client_id)
        if not client:
            return False, "❌ Клиент не найден"
        purchases_count = await session.scalar(
            select(func.count()).select_from(Purchase).where(Purchase.client_id == client_id)
        )
        return True, (
            f"Удалить клиента **{client.full_name}** и все его покупки ({purchases_count} шт.)?"
        )


# ====================== УДАЛЕНИЕ ПОКУПКИ ======================
async def delete_purchase_by_id(purchase_id: int) -> Tuple[bool, str]:
    async with get_async_session_factory()() as session:
        purchase = await session.get(Purchase, purchase_id)
        if not purchase:
            return False, "❌ Покупка не найдена"
        return True, f"Удалить покупку №{purchase_id} на сумму {purchase.total_amount} ₽?"


# ====================== ЭКСПОРТ ======================
async def export_clients_csv() -> str:
    rows = await ClientRepository.get_all_clients_for_export()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ID', 'ФИО', 'Телефон', 'Telegram', 'Дата регистрации'])
        for row in rows:
            writer.writerow([
                row.id,
                row.full_name,
                row.phone,
                row.telegram_username,
                row.created_at.strftime("%d.%m.%Y %H:%M")
            ])
        return f.name


async def export_purchases_csv() -> str:
    rows = await ClientRepository.get_all_purchases_for_export()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ID покупки', 'Клиент', 'Дата', 'Сумма', 'Тип', 'Способ оплаты'])
        for row in rows:
            writer.writerow([
                row.id,
                row.client_name,
                row.created_at.strftime("%d.%m.%Y"),
                row.total_amount,
                row.purchase_type,
                row.payment_details
            ])
        return f.name


async def export_full_report_csv() -> str:
    rows = await ClientRepository.get_full_report()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Клиент', 'Телефон', 'Покупка', 'Дата', 'Сумма', 'Товары'])
        for row in rows:
            writer.writerow([
                row.client_name,
                row.phone,
                row.purchase_id,
                row.created_at.strftime("%d.%m.%Y"),
                row.total_amount,
                row.items_text
            ])
        return f.name


async def get_client_info_text(query: str) -> str | None:
    client = await ClientRepository.find_by_phone_or_name(query)
    if not client:
        return None
    return (
        f"👤 **{client.full_name}**\n"
        f"📱 Телефон: {client.phone}\n"
        f"🔗 Telegram: @{client.telegram_username or '—'}\n"
        f"📅 Зарегистрирован: {client.created_at.strftime('%d.%m.%Y')}"
    )


async def list_categories_text() -> str:
    async with get_async_session_factory()() as session:
        cats = await session.execute(select(Category).order_by(Category.name))
        cats = cats.scalars().all()
    if not cats:
        return "📭 Категорий пока нет."
    return "📋 **Список категорий**\n\n" + "\n".join(
        f"`{c.id}` — {escape_markdown_v1(c.name)}" for c in cats
    )


async def find_empty_categories():
    async with get_async_session_factory()() as session:
        result = await session.execute(
            select(Category.id, Category.name)
            .outerjoin(Item, Category.id == Item.category_id)
            .group_by(Category.id, Category.name)
            .having(func.count(Item.id) == 0)
        )
        return result.all()


async def undo_last_deletion() -> str:
    # TODO: Реализовать полноценное восстановление последнего удаления
    # В текущей версии можно добавить логику восстановления из deleted_items
    return "✅ Функция восстановления последнего удаления пока в разработке"


async def fix_sales_unique() -> str:
    # TODO: Добавить проверку и исправление уникальности message_id в продажах
    return "✅ Функция исправления уникальности продаж пока в разработке"


async def set_webhook_manually() -> str:
    from aiogram import Bot
    if not config.RENDER_URL:
        return "❌ RENDER_URL не задан в .env"
    bot = Bot(token=config.BOT_TOKEN)
    webhook_url = f"{config.RENDER_URL.rstrip('/')}/webhook"
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(url=webhook_url)
        await bot.session.close()
        logger.info(f"✅ Вебхук вручную установлен: {webhook_url}")
        return f"✅ Вебхук успешно установлен:\n{webhook_url}"
    except Exception as e:
        await bot.session.close()
        logger.exception("Ошибка установки вебхука")
        return f"❌ Ошибка установки вебхука: {e}"
