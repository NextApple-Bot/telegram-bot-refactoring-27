import logging
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError

from bot import config

logger = logging.getLogger(__name__)

# Флаг, чтобы не спамить WARNING каждый раз при проверке вебхука
_webhook_mismatch_logged = False


async def check_and_set_webhook(
    bot: Optional[Bot] = None,
    dp: Optional[Dispatcher] = None,
    force: bool = False,
) -> bool:
    """
    Проверяет текущий вебхук Telegram и при необходимости переустанавливает его.

    Функция идемпотентна: если вебхук уже установлен на правильный URL,
    повторная установка не происходит.
    """
    global _webhook_mismatch_logged

    if not bot:
        logger.error("❌ Невозможно проверить вебхук: объект Bot не передан")
        return False

    if not config.RENDER_URL:
        logger.warning("⚠️ RENDER_URL не задан — установка вебхука пропущена")
        return False

    expected_url = f"{config.RENDER_URL}/webhook".rstrip("/")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/getWebhookInfo",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        if not data.get("ok"):
            logger.error(f"❌ Ошибка получения информации о вебхуке: {data}")
            return False

        current_url = data["result"].get("url", "")

        if current_url == expected_url and not force:
            if _webhook_mismatch_logged:
                logger.info(f"✅ Вебхук корректен: {expected_url}")
                _webhook_mismatch_logged = False
            return True

        if current_url != expected_url:
            if not _webhook_mismatch_logged:
                logger.warning(
                    f"⚠️ Вебхук не соответствует ожидаемому.\n"
                    f"   Текущий:   {
