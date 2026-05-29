import logging
import os

from aiogram import Router
from aiogram.types import Message


from bot.services.assortment import AssortmentService

router = Router()
logger = logging.getLogger(__name__)


@router.message()
async def handle_arrival_file(message: Message):
    """Обработка файлов с новым ассортиментом (Excel или TXT)."""
    if not message.document:
        return

    file_name = message.document.file_name.lower()

    # Поддерживаемые форматы
    if file_name.endswith(('.xlsx', '.xls')):
        file_type = 'excel'
    elif file_name.endswith('.txt'):
        file_type = 'txt'
    else:
        await message.answer("❌ Поддерживаются только Excel (.xlsx, .xls) и TXT файлы")
        return

    # Скачиваем файл
    file_path = None
    try:
        file = await message.bot.get_file(message.document.file_id)
        ext = '.xlsx' if file_type == 'excel' else '.txt'
        file_path = f"/tmp/{message.document.file_id}{ext}"
        await message.bot.download_file(file.file_path, file_path)

        # Импортируем
        if file_type == 'excel':
            result = await AssortmentService.import_arrival_from_excel(file_path)
        else:
            result = await AssortmentService.import_arrival_from_txt(file_path)

        if result.get("success"):
            text = (
                f"✅ **Ассортимент успешно обновлён!**\n\n"
                f"• Новых категорий: {result.get('added_categories', 0)}\n"
                f"• Новых товаров: {result.get('added_items', 0)}\n"
                f"• Обновлено цен: {result.get('updated_items', 0)}"
            )
            await message.answer(text, parse_mode="Markdown")
        else:
            await message.answer(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")

    except Exception as e:
        logger.exception("Ошибка обработки файла прибытия")
        await message.answer("❌ Произошла ошибка при обработке файла.")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
