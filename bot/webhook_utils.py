# Файл: bot/webhook_utils.py
import logging

import aiohttp
from aiogram import Bot, Dispatcher

from bot.config import config

logger = logging.getLogger(__name__)


async def check_and_set_webhook(bot: Bot = None, dp: Dispatcher = None):
    """Проверяет текущий вебхук через Telegram API и переустанавливает, если нужно."""
    if not bot or not config.RENDER_URL:
        logger.warning("❌ Нельзя проверить вебхук: бот или RENDER_URL не заданы")
        return

    expected_url = f"{config.RENDER_URL}/webhook"
    try:
        async with aiohttp.ClientSession() as session, session.get(f"https://api.telegram.org/bot{config.BOT_TOKEN}/getWebhookInfo") as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.error(f"Ошибка получения информации о вебхуке: {data}")
                return
            current_url = data["result"].get("url", "")
            if current_url != expected_url:
                logger.warning(f"Вебхук не соответствует: ожидается {expected_url}, сейчас {current_url}. Переустанавливаем...")
                await bot.delete_webhook(drop_pending_updates=True)
                allowed_updates = dp.resolve_used_update_types() if dp else None
                await bot.set_webhook(url=expected_url, allowed_updates=allowed_updates)
                logger.info(f"✅ Вебхук переустановлен на {expected_url}")
            else:
                logger.debug(f"Вебхук корректен: {expected_url}")
    except Exception as e:
        logger.error(f"Ошибка при проверке вебхука: {e}")
