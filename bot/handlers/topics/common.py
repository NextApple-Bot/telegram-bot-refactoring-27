import os
import tempfile
from datetime import datetime

from aiogram import Bot
from aiogram.types import FSInputFile

from bot import config
from bot.services.assortment import AssortmentService
from bot.utils.sort import build_output_text


async def export_assortment_to_topic(bot: Bot, admin_id: int):
    """Выгружает текущий ассортимент в топик «Ассортимент» и уведомляет админа."""
    categories = await AssortmentService.load_inventory()
    if not categories:
        await bot.send_message(admin_id, "📭 Ассортимент пуст, нечего выгружать.")
        return
    text = build_output_text(categories)
    today = datetime.now().strftime("%d.%m.%Y")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp_path = f.name
    try:
        document = FSInputFile(tmp_path, filename=f"assortiment_{today}.txt")
        await bot.send_document(
            chat_id=config.MAIN_GROUP_ID,
            document=document,
            caption=f"📦 Текущий ассортимент (категорий: {len(categories)})",
            message_thread_id=config.THREAD_ASSORTMENT
        )
        await bot.send_message(admin_id, "✅ Ассортимент успешно выгружен в топик «Ассортимент».")
    finally:
        os.unlink(tmp_path)
