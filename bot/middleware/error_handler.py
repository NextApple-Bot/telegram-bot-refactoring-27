import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """Глобальный обработчик ошибок."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)

        except Exception as exc:
            user: User | None = data.get("event_from_user")
            user_info = f"{user.id} ({user.full_name})" if user else "Unknown"

            logger.error(
                f"❌ Критическая ошибка в обработчике\n"
                f"Пользователь: {user_info}\n"
                f"Тип события: {type(event).__name__}\n"
                f"{traceback.format_exc()}"
            )

            # Асинхронное уведомление админов
            asyncio.create_task(self._notify_admins(exc, user))

            # Пробуем ответить пользователю
            try:
                bot = data.get("bot")
                if bot and user:
                    await bot.send_message(
                        user.id,
                        "❌ Произошла внутренняя ошибка.\nМы уже уведомлены и исправим её."
                    )
            except Exception:
                pass

            return None  # не ломаем бота

    async def _notify_admins(self, exc: Exception, user: User | None):
        try:
            from telegram_alerter import send_alert
            msg = (
                f"🚨 Ошибка в боте\n"
                f"Пользователь: {user.full_name if user else 'Unknown'}\n"
                f"Ошибка: {type(exc).__name__}: {exc}"
            )
            await send_alert(msg, is_critical=True)
        except Exception as e:
            logger.error(f"Не удалось отправить алерт: {e}")
