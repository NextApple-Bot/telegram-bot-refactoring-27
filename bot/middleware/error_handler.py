import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

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
            update_id = getattr(event, "update_id", None)
            user_id = None
            chat_id = None
            event_type = type(event).__name__

            try:
                if hasattr(event, "message") and event.message:
                    user_id = event.message.from_user.id if event.message.from_user else None
                    chat_id = event.message.chat.id
                elif hasattr(event, "callback_query") and event.callback_query:
                    user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
                    chat_id = event.callback_query.message.chat.id if event.callback_query.message else None
            except Exception:
                pass

            logger.error(
                f"❌ Ошибка при обработке Update #{update_id}\n"
                f"Тип события: {event_type}\n"
                f"User ID: {user_id}\n"
                f"Chat ID: {chat_id}\n"
                f"Ошибка: {exc}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )

            try:
                admin_ids = getattr(config, "ADMIN_IDS", [])
                if admin_ids:
                    alert_text = (
                        f"🚨 <b>Критическая ошибка в боте</b>\n\n"
                        f"<b>Update ID:</b> {update_id}\n"
                        f"<b>Тип:</b> {event_type}\n"
                        f"<b>Пользователь:</b> {user_id}\n"
                        f"<b>Ошибка:</b> {str(exc)[:400]}"
                    )
                    for admin_id in admin_ids:
                        if admin_id:
                            try:
                                await send_alert(alert_text, admin_id)
                            except Exception as alert_error:
                                logger.warning(f"Не удалось отправить алерт админу {admin_id}: {alert_error}")
            except Exception as e:
                logger.error(f"Ошибка при отправке алерта: {e}")

            raise
