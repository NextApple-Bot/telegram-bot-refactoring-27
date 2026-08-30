"""Простой audit log действий админки."""
from __future__ import annotations

import logging
from typing import Any

from starlette.requests import Request

from bot.db import get_async_session_factory
from bot.models import AdminAuditLog

logger = logging.getLogger(__name__)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return None


async def log_admin_action(
    action: str,
    detail: str | None = None,
    request: Request | None = None,
    **extra: Any,
) -> None:
    """Пишет запись в admin_audit_logs. Ошибки не пробрасывает."""
    try:
        parts = []
        if detail:
            parts.append(str(detail))
        if extra:
            parts.append(
                ", ".join(f"{k}={v}" for k, v in extra.items() if v is not None)
            )
        text = "; ".join(parts) if parts else None
        if text and len(text) > 2000:
            text = text[:2000]

        async_session = get_async_session_factory()
        async with async_session() as session:
            session.add(
                AdminAuditLog(
                    action=(action or "unknown")[:64],
                    detail=text,
                    ip=_client_ip(request),
                )
            )
            await session.commit()
    except Exception:
        logger.exception("Не удалось записать audit action=%s", action)
