"""In-memory rate limiting for HTTP (per-process).

Not a substitute for Redis/edge limits under multi-replica, but blocks
simple abuse (login brute-force, spam) on a single instance.
"""
from __future__ import annotations

import functools
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# key -> list of timestamps
_request_times: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT = 60
TIME_WINDOW = 60

# Paths that must never be rate-limited (Telegram + probes)
_EXEMPT_PREFIXES = (
    "/webhook",
    "/health",
    "/metrics",
)


def _client_ip(request: Request) -> str:
    # Respect reverse proxy if present
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune(key: str, now: float, window_seconds: int) -> list[float]:
    times = [t for t in _request_times[key] if now - t < window_seconds]
    _request_times[key] = times
    return times


def allow_request(key: str, max_calls: int, window_seconds: int) -> bool:
    """Return True if the call is within limit; record it on success."""
    now = time.time()
    times = _prune(key, now, window_seconds)
    if len(times) >= max_calls:
        return False
    times.append(now)
    _request_times[key] = times
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global per-IP limit for the Starlette/FastAPI app."""

    def __init__(
        self,
        app,
        max_calls: int = RATE_LIMIT,
        window_seconds: int = TIME_WINDOW,
        exempt_prefixes: tuple[str, ...] = _EXEMPT_PREFIXES,
    ):
        super().__init__(app)
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.exempt_prefixes = exempt_prefixes

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if any(path == p or path.startswith(p + "/") for p in self.exempt_prefixes):
            return await call_next(request)

        ip = _client_ip(request)
        key = f"mw:{ip}"
        if not allow_request(key, self.max_calls, self.window_seconds):
            logger.warning("Rate limit exceeded for %s path=%s", ip, path)
            return JSONResponse(
                {"detail": "Too Many Requests"},
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
            )
        return await call_next(request)


def rate_limit(
    max_calls: int = RATE_LIMIT,
    window_seconds: int = TIME_WINDOW,
    *,
    scope: str | None = None,
) -> Callable:
    """
    Per-route rate limit (per IP).
    Use on login and other sensitive endpoints with a tighter budget.
    """

    def decorator(func: Callable) -> Callable:
        limit_scope = scope or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any):
            request = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break
            if isinstance(request, Request):
                ip = _client_ip(request)
                key = f"rl:{limit_scope}:{ip}"
                if not allow_request(key, max_calls, window_seconds):
                    logger.warning(
                        "Route rate limit exceeded scope=%s ip=%s", limit_scope, ip
                    )
                    return JSONResponse(
                        {
                            "detail": "Too Many Requests",
                            "error": "Слишком много попыток. Подождите минуту.",
                        },
                        status_code=429,
                        headers={"Retry-After": str(window_seconds)},
                    )
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            request = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break
            if isinstance(request, Request):
                ip = _client_ip(request)
                key = f"rl:{limit_scope}:{ip}"
                if not allow_request(key, max_calls, window_seconds):
                    return JSONResponse(
                        {"detail": "Too Many Requests"},
                        status_code=429,
                        headers={"Retry-After": str(window_seconds)},
                    )
            return func(*args, **kwargs)

        if functools.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


__all__ = ["RateLimitMiddleware", "rate_limit", "allow_request"]
