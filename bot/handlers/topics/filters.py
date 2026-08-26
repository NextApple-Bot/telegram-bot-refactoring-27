"""Фильтры топиков forum-группы.

Важно: фильтр должен стоять на декораторе @router.message(...),
а не только внутри хендлера. Иначе первый роутер с широким
F.text «съедает» событие и остальные топики его не видят.
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot import config

logger = logging.getLogger(__name__)


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


class InMainGroup(Filter):
    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat
        if chat is None:
            return False
        got = _as_int(chat.id)
        expected = _as_int(config.MAIN_GROUP_ID)
        return got is not None and expected is not None and got == expected


class InTopic(Filter):
    """Сообщение / callback в конкретном message_thread_id."""

    def __init__(self, thread_attr: str, label: str = "topic") -> None:
        self.thread_attr = thread_attr
        self.label = label

    def _expected(self) -> int | None:
        return _as_int(getattr(config, self.thread_attr, None))

    async def __call__(self, event: TelegramObject, **kwargs: Any) -> bool:
        msg: Message | None = None
        if isinstance(event, Message):
            msg = event
        elif isinstance(event, CallbackQuery):
            msg = event.message

        if msg is None:
            return False

        got = _as_int(msg.message_thread_id)
        expected = self._expected()
        ok = got is not None and expected is not None and got == expected
        if not ok:
            logger.debug(
                "%s filter miss: got=%s expected=%s chat=%s",
                self.label,
                got,
                expected,
                getattr(msg.chat, "id", None),
            )
        return ok


# Готовые фильтры под каждый топик
in_main_group = InMainGroup()
in_sales = InTopic("THREAD_SALES", "sales")
in_assortment = InTopic("THREAD_ASSORTMENT", "assortment")
in_arrival = InTopic("THREAD_ARRIVAL", "arrival")
in_preorder = InTopic("THREAD_PREORDER", "preorder")
