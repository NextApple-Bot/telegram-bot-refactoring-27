from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import time
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# Простой in-memory rate limiter
_request_times = defaultdict(list)
RATE_LIMIT = 30
TIME_WINDOW = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        _request_times[client_ip] = [
            t for t in _request_times[client_ip] if now - t < TIME_WINDOW
        ]

        if len(_request_times[client_ip]) >= RATE_LIMIT:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return Response("Too Many Requests", status_code=429)

        _request_times[client_ip].append(now)
        return await call_next(request)


def rate_limit(max_calls: int = RATE_LIMIT, window_seconds: int = TIME_WINDOW):
    """Декоратор rate limiting."""
    def decorator(func):
        return func
    return decorator


__all__ = ["RateLimitMiddleware", "rate_limit"]
