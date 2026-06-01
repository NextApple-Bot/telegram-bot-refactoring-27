import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery

from bot import config
from telegram_alerter import send_alert

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)

        except Exception as exc:
            # Получаем информацию о событии
            update_id = getattr(event, "update_id", "unknown")
            user_id = None
            chat_id = None
            message_text = None

            # Пытаемся вытащить пользователя и чат
            if isinstance(event, Update):
                if event.message:
                    user_id = event.message.from_user.id if event.message.from_user else None
                    chat_id = event.message.chat.id
                    message_text = event.message.text or event.message.caption
                elif event.callback_query:
                    user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
                    chat_id = event.callback_query.message.chat.id if event.callback_query.message else None
                    message_text = event.callback_query.data

            # Логируем ошибку подробно
            logger.exception(
                f"❌ Критическая ошибка в обработчике\n"
                f"Update ID: {update_id}\n"
                f"User ID: {user_id}\n"
                f"Chat ID: {chat_id}\n"
                f"Text/Data: {message_text}\n"
                f"Error: {exc}"
            )

            # Отправляем алерт админам (только на валидные ID)
            try:
                admin_ids = config.ADMIN_IDS if hasattr(config, "ADMIN_IDS") else []
                error_text = (
                    f"🚨 <b>Ошибка в боте</b>\n\n"
                    f"<b>Пользователь:</b> {user_id}\n"
                    f"<b>Ошибка:</b> {str(exc)[:300]}\n"
                    f"<b>Update ID:</b> {update_id}"
                )
                for admin_id in admin_ids:
                    if admin_id:  # защита от пустых/неверных ID
                        await send_alert(error_text, admin_id)
            except Exception as alert_exc:
                logger.error(f"Не удалось отправить алерт админу: {alert_exc}")

            # Пробрасываем ошибку дальше (чтобы aiogram мог обработать)
            raise
