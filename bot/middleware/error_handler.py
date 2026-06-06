import logging
from collections.abc import Awaitable, Callable
from typing import Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
logger = logging.getLogger(__name__)
class ErrorHandlerMiddleware(BaseMiddleware[TelegramObject, dict[str, Any]]):
    """
    Глобальный middleware для обработки ошибок в aiogram 3.
    Перехватывает все необработанные исключения, возникающие в хендлерах
    (message, callback_query, inline_query и т.д.).
    Особенности:
    - Логирует ошибку с контекстом (тип события, update_id при наличии).
    - Не ломает работу бота — возвращает None при возникновении ошибки.
    - Готов к интеграции с Sentry / другими системами мониторинга.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Выполняет хендлер и перехватывает исключения.
        Args:
            handler: Оригинальный хендлер события.
            event: Объект события (Message, CallbackQuery и т.д.).
            data: Данные, передаваемые в хендлер.
        Returns:
            Результат выполнения хендлера или None в случае ошибки.
        """
        try:
            return await handler(event, data)
        except Exception as exc:
            # Собираем контекст для логирования
            event_type = type(event).__name__
            # Пытаемся получить update_id (если доступен)
            update_id = self._extract_update_id(event, data)
            logger.exception(
                "Необработанная ошибка в хендлере aiogram",
                exc_info=exc,
                extra={
                    "event_type": event_type,
                    "update_id": update_id,
                },
            )
            # TODO: Интеграция с Sentry / Alerting
            # import sentry_sdk
            # sentry_sdk.capture_exception(exc)
            # Возвращаем None, чтобы не прерывать обработку других middleware/хендлеров
            return None
    @staticmethod
    def _extract_update_id(event: TelegramObject, data: dict[str, Any]) -> int | None:
        """
        Пытается извлечь update_id из события или данных middleware.
        """
        # Вариант 1: событие само содержит update_id (редко)
        if hasattr(event, "update_id"):
            return getattr(event, "update_id", None)
        # Вариант 2: update находится в data (стандартный способ в aiogram 3)
        update = data.get("event_update")
        if update is not None and hasattr(update, "update_id"):
            return getattr(update, "update_id", None)
        return None
