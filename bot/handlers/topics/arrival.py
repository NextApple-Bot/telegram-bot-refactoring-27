import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.states import ArrivalConfirmState
from bot.models import Item
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)
router = Router()


async def determine_category_for_item(item_text: str, categories: list) -> str:
    stripped = item_text.strip()
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()
    best_match = None
    best_len = 0

    for cat in categories:
        cat_name = normalize_name(str(cat.get('header') or cat.get('name', ''))).lower().rstrip(':')
        if not cat_name:
            continue
        if base.startswith(cat_name) and len(cat_name) > best_len:
            best_len = len(cat_name)
            best_match = cat.get('header') or cat.get('name')
        elif cat_name in base and len(cat_name) > best_len:
            best_len = len(cat_name)
            best_match = cat.get('header') or cat.get('name')

    if best_match:
        return best_match

    if 'iphone' in item_text.lower():
        return f"{extract_base_name(item_text)}:"

    if ',' in item_text:
        new_header = item_text.split(',')[0].strip() + ':'
    else:
        words = item_text.split()
        new_header = ' '.join(words[:2]).strip() + ':'

    return normalize_name(new_header)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption)
)
async def handle_arrival(message: Message, state: FSMContext):
    try:
        content = message.text or message.caption
        if not content:
            await message.reply("⚠️ Отправь текст с товарами.")
            return

        logger.info(f"📥 Получено сообщение в Arrival (chat_id={message.chat.id})")

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        lines = [line for line in lines if not re.match(r'^[-–—\s]+$', line)]
        lines_with_serial = [line for line in lines if extract_serials(line)]

        logger.info(f"Найдено строк с серийными номерами: {len(lines_with_serial)}")

        if not lines_with_serial:
            await message.reply("❌ В сообщении нет строк с серийными номерами.")
            return

        current_categories = await AssortmentService.load_inventory()

        parsed_items = []
        for line in lines_with_serial:
            serials = extract_serials(line)
            serial = serials[0] if serials else None
            category = await determine_category_for_item(line, current_categories)
            parsed_items.append({
                "text": line,
                "serial": serial,
                "category": category
            })

        if not parsed_items:
            await message.reply("❌ Не удалось распознать товары.")
            return

        logger.info(f"Успешно распознано товаров для добавления: {len(parsed_items)}")

        await state.update_data(temp_items=parsed_items)
        await state.set_state(ArrivalConfirmState.waiting_for_confirm)

        preview = f"📥 Найдено **{len(parsed_items)}** товаров.\n\n"
        for item in parsed_items[:8]:
            preview += f"• {item['text'][:70]}\n"
        if len(parsed_items) > 8:
            preview += f"... и ещё {len(parsed_items)-8}\n"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Добавить в ассортимент", callback_data="arrival_confirm:yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_confirm:no")]
        ])

        await message.reply(preview, reply_markup=keyboard)

    except Exception as e:
        logger.exception("Ошибка в handle_arrival")
        await message.reply(f"❌ Ошибка: {str(e)[:100]}")


@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("temp_items", [])
    action = callback.data.split(":")[1]

    if action != "yes" or not items:
        await callback.message.edit_text("❌ Добавление отменено.")
        await state.clear()
        await callback.answer()
        return

    logger.info(f"🚀 Начинаем добавление {len(items)} товаров из Arrival")

    added = 0
    skipped_duplicates = 0
    failed = 0

    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            for item in items:
                try:
                    if item.get("serial"):
                        existing = await session.scalar(
                            select(Item.id).where(Item.serial == item["serial"])
                        )
                        if existing:
                            skipped_duplicates += 1
                            logger.info(f"⏭ Пропущен дубликат: {item['serial']}")
                            continue

                    cat_id = await ItemRepository.get_or_create_category(item["category"], conn=session)

                    from bot.models import Item as ItemModel
                    session.add(ItemModel(
                        text=item["text"],
                        serial=item.get("serial"),
                        category_id=cat_id
                    ))
                    added += 1
                    logger.debug(f"✅ Добавлен товар: {item['text'][:60]}")

                except Exception as e:
                    failed += 1
                    logger.warning(f"❌ Ошибка добавления товара: {item['text'][:60]} | {e}")

        try:
            await AssortmentService.invalidate_cache()
        except Exception:
            pass

        text = f"✅ **Добавлено:** {added} товаров\n"
        if skipped_duplicates > 0:
            text += f"⏭ **Пропущено дублей:** {skipped_duplicates}\n"
        if failed > 0:
            text += f"❌ **Ошибок:** {failed}\n"

        await callback.message.edit_text(text)
        logger.info(f"✅ Завершено добавление. Добавлено: {added}, дублей: {skipped_duplicates}, ошибок: {failed}")

    except Exception as e:
        logger.exception("Критическая ошибка при массовом добавлении товаров")
        await callback.message.edit_text(f"❌ Произошла ошибка при добавлении: {e}")

    await state.clear()
    await callback.answer()
