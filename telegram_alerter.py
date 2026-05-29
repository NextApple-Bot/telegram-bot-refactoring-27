import asyncio
import logging
import os

from aiogram import Bot

from bot.config import config

logger = logging.getLogger(__name__)


async def send_alert(message: str, is_critical: bool = False):
    """
    Отправляет алерт всем администраторам.
    """
    if not config.BOT_TOKEN or not config.ADMIN_IDS:
        logger.error("❌ Не могу отправить алерт: BOT_TOKEN или ADMIN_IDS не настроены")
        return

    prefix = "🚨 КРИТИЧЕСКАЯ ОШИБКА" if is_critical else "⚠️ Уведомление"
    full_message = f"{prefix}\n\n{message}"

    bot = Bot(token=config.BOT_TOKEN)

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=full_message,
                parse_mode="HTML"
            )
            logger.info(f"✅ Алерт отправлен админу {admin_id}")
        except Exception as e:
            logger.error(f"❌ Не удалось отправить алерт админу {admin_id}: {e}")

    await bot.session.close()


# Для теста
if __name__ == "__main__":
    asyncio.run(send_alert("Тестовый алерт из telegram_alerter.py"))
