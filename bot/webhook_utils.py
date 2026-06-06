import logging
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError

from bot import config

logger = logging.getLogger(__name__)


async def check_and_set_webhook(
    bot: Optional[Bot] = None,
    dp: Optional[Dispatcher] = None,
    force: bool = False,
) -> bool:
    """
    Проверяет текущий вебхук Telegram и при необходимости переустанавливает его.

    Функция идемпотентна: если вебхук уже установлен на правильный URL,
    повторная установка не происходит.

    Args:
        bot: Экземпляр бота. Если не передан — функция завершится.
        dp: Dispatcher (нужен для получения списка allowed_updates).
        force: Если True — принудительно пересоздаёт вебхук, даже если URL совпадает.

    Returns:
        True, если вебхук успешно установлен/проверен, иначе False.
    """
    if not bot:
        logger.error("❌ Невозможно проверить вебхук: объект Bot не передан")
        return False

    if not config.RENDER_URL:
        logger.warning("⚠️ RENDER_URL не задан — установка вебхука пропущена")
        return False

    expected_url = f"{config.RENDER_URL}/webhook".rstrip("/")

    try:
        # Получаем текущую информацию о вебхуке
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

        # Если URL совпадает и не требуется принудительная переустановка — выходим
        if current_url == expected_url and not force:
            logger.info(f"✅ Вебхук уже корректно настроен: {expected_url}")
            return True

        # Нужно установить/переустановить вебхук
        if current_url:
            logger.warning(
                f"⚠️ Вебхук не соответствует ожидаемому.\n"
                f"   Текущий:   {current_url}\n"
                f"   Ожидаемый: {expected_url}"
            )
        else:
            logger.info("ℹ️ Вебхук не установлен. Выполняем первоначальную настройку...")

        # Удаляем старый вебхук (с очисткой pending updates)
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🗑️ Старый вебхук удалён")

        # Получаем список используемых типов обновлений
        allowed_updates = dp.resolve_used_update_types() if dp else None

        # Устанавливаем новый вебхук
        await bot.set_webhook(
            url=expected_url,
            allowed_updates=allowed_updates,
            drop_pending_updates=True,
        )

        logger.info(f"✅ Вебхук успешно установлен: {expected_url}")
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
    """
    Принудительно удаляет текущий вебхук.
    Полезно при переключении между webhook и long polling.
    """
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхук успешно удалён")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении вебхука: {e}")
        return False
