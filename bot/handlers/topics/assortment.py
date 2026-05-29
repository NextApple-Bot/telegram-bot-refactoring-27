import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.types.input_file import BufferedInputFile

from bot import config
from bot.handlers.states import AssortmentConfirmState
from bot.services.assortment import AssortmentService
from bot.utils.sort import build_output_text, sort_assortment_to_categories

logger = logging.getLogger(__name__)
router = Router()


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ASSORTMENT,
    (F.text | F.document)
)
async def handle_assortment_upload(message: Message, state: FSMContext):
    """
    Обработка текстового сообщения или файла .txt с ассортиментом.
    """
    content = None

    # Если прислали документ
    if message.document:
        if not message.document.file_name.endswith('.txt'):
            await message.reply("❌ Поддерживаются только текстовые файлы (.txt).")
            return
        if message.document.file_size > 10 * 1024 * 1024:
            await message.reply("❌ Файл слишком большой (максимум 10 МБ).")
            return
        file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        content = file_bytes.read().decode('utf-8')
    # Если прислали текст
    elif message.text:
        content = message.text
    else:
        await message.reply("❌ Отправьте текстовый файл (.txt) или текстовое сообщение с ассортиментом.")
        return

    # Парсим ассортимент в категории
    categories = sort_assortment_to_categories(content)
    if not categories:
        await message.reply("❌ Не удалось распознать ассортимент. Проверьте формат.\n"
                            "Ожидается:\n"
                            "---\n"
                            "Категория:\n"
                            "---\n"
                            "Товар 1 (SN123)\n"
                            "Товар 2 (SN456)\n"
                            "---\n"
                            "Другая категория:\n"
                            "---\n"
                            "...")
        return

    # Сохраняем во временное состояние
    await state.update_data(temp_categories=categories)
    await state.set_state(AssortmentConfirmState.waiting_for_confirm)

    # Показываем предпросмотр и кнопки подтверждения
    preview = f"📦 Найдено категорий: {len(categories)}\n\n"
    for cat in categories[:5]:  # показываем первые 5 категорий
        preview += f"• {cat['header']} — {len(cat['items'])} товаров\n"
    if len(categories) > 5:
        preview += f"... и ещё {len(categories)-5} категорий."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Заменить ассортимент", callback_data="assort_confirm:yes")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="assort_confirm:no")]
    ])
    await message.reply(preview, reply_markup=keyboard)


@router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    categories = data.get("temp_categories")
    action = callback.data.split(":")[1]

    if action == "yes" and categories:
        try:
            await AssortmentService.save_inventory(categories)
            await callback.message.edit_text("✅ Ассортимент успешно загружен и сохранён.")
        except Exception as e:
            logger.exception("Ошибка сохранения ассортимента")
            await callback.message.edit_text(f"❌ Ошибка при сохранении: {e}")
    else:
        await callback.message.edit_text("❌ Загрузка ассортимента отменена.")
    await state.clear()
    await callback.answer()


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ASSORTMENT,
    F.text == "/export_assortment"
)
async def export_assortment(message: Message):
    """Команда для выгрузки текущего ассортимента в топик (только для админов)."""
    categories = await AssortmentService.load_inventory()
    if not categories:
        await message.reply("📭 Ассортимент пуст.")
        return
    text = build_output_text(categories)
    if len(text) > 4096:
        # Отправляем файлом
        await message.answer_document(BufferedInputFile(text.encode(), filename="assortment.txt"))
    else:
        await message.answer(text)
