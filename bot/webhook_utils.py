import logging
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError

from bot import config

logger = logging.getLogger(__name__)

# Флаг, чтобы не спамить WARNING каждый раз
_webhook_mismatch_logged = False


async def check_and_set_webhook(
    bot: Optional[Bot] = None,
    dp: Optional[Dispatcher] = None,
    force: bool = False,
) -> bool:
    """
    Проверяет текущий вебхук Telegram и при необходимости переустанавливает его.
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

        # Логируем mismatch только один раз
        if current_url != expected_url:
            if not _webhook_mismatch_logged:
                logger.warning(
                    f"⚠️ Вебхук не соответствует ожидаемому.\n"
                    f"   Текущий:   {current_url}\n"
                    f"   Ожидаемый: {expected_url}\n"
                    f"   Выполняем переустановку..."
                )
                _webhook_mismatch_logged = True
        else:
            _webhook_mismatch_logged = False

        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🗑️ Старый вебхук удалён")

        allowed_updates = dp.resolve_used_update_types() if dp else None

        await bot.set_webhook(
            url=expected_url,
            allowed_updates=allowed_updates,
            drop_pending_updates=True,
        )

        logger.info(f"✅ Вебхук успешно установлен: {expected_url}")
        _webhook_mismatch_logged = False
        return True

    except TelegramAPIError as e:
        logger.error(f"❌ Ошибка Telegram API при настройке вебхука: {e}")
        return False
    except aiohttp.ClientError as e:
        logger.error(f"❌ Сетевая ошибка при проверке вебхука: {e}")
        return False
    except Exception as e:
        logger.exception(f"❌ Неожиданная ошибка при настройке вебхука: {e}")
        return False


async def delete_webhook(bot: Bot) -> bool:
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхук успешно удалён")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении вебхука: {e}")
        return False
