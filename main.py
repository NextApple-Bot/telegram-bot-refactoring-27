import asyncio
import logging
import os
import signal
import sys
import time
import traceback

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class Application:
    def __init__(self):
        from bot.config import config

        self.config = config
        self.bot = None
        self.dp = None
        self._shutdown = False

    async def startup(self):
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.fsm.storage.memory import MemoryStorage

        from bot.db import init_db
        from bot.handlers import router as root_router
        from bot.middleware.error_handler import ErrorHandlerMiddleware
        from bot.webhook_utils import check_and_set_webhook

        await init_db()

        storage = MemoryStorage()
        if self.config.REDIS_URL:
            try:
                from aiogram.fsm.storage.redis import RedisStorage
                from redis.asyncio import Redis

                redis = Redis.from_url(self.config.REDIS_URL)
                storage = RedisStorage(redis=redis)
                logger.info("✅ Redis FSM storage")
            except Exception as e:
                logger.warning("⚠️ Redis FSM недоступен, MemoryStorage: %s", e)
        else:
            logger.warning(
                "⚠️ REDIS_URL не задан — MemoryStorage. Состояния FSM сбрасываются при рестарте. Добавьте Redis в Amvera и переменную REDIS_URL."
            )

        self.bot = Bot(
            token=self.config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = Dispatcher(storage=storage)
        self.dp.message.middleware(ErrorHandlerMiddleware())
        self.dp.callback_query.middleware(ErrorHandlerMiddleware())
        self.dp.include_router(root_router)

        await check_and_set_webhook(self.bot, self.dp)

        from bot.background import start_background_tasks

        await start_background_tasks(self.bot)

    async def shutdown(self):
        self._shutdown = True
        try:
            if self.bot:
                await self.bot.session.close()
        except Exception as e:
            logger.error(f"Ошибка в shutdown: {e}")

    async def webhook(self, request: Request) -> Response:
        if not self.bot or not self.dp:
            return Response(status_code=503)
        try:
            from aiogram.types import Update

            update_data = await request.json()
            update = Update(**update_data)
            await self.dp.feed_update(bot=self.bot, update=update)
            return Response(status_code=200)
        except Exception as e:
            logger.exception(f"Ошибка обработки webhook: {e}")
            return Response(status_code=500)

    async def health(self, _: Request) -> Response:
        return PlainTextResponse("ok")

    async def health_detailed(self, _: Request) -> Response:
        from bot.db import check_db_health, check_redis_health

        start = time.monotonic()
        db_ok = await check_db_health()
        db_time = time.monotonic() - start
        start = time.monotonic()
        redis_ok = await check_redis_health()
        redis_time = time.monotonic() - start
        overall = db_ok  # redis optional for health
        return JSONResponse(
            {
                "status": "healthy" if overall else "unhealthy",
                "database": {
                    "status": "up" if db_ok else "down",
                    "response_time_ms": round(db_time * 1000, 2) if db_ok else None,
                },
                "redis": {
                    "status": "up" if redis_ok else "down",
                    "response_time_ms": round(redis_time * 1000, 2) if redis_ok else None,
                },
            },
            status_code=200 if overall else 503,
        )


def create_starlette_app(app_instance):
    from starlette.routing import Route

    routes = [
        Route("/webhook", app_instance.webhook, methods=["POST"]),
        Route("/health", app_instance.health, methods=["GET"]),
        Route("/health/detailed", app_instance.health_detailed, methods=["GET"]),
        Route("/", lambda req: RedirectResponse(url="/admin/dashboard")),
    ]
    starlette_app = Starlette(routes=routes)

    Instrumentator().instrument(starlette_app).expose(starlette_app, endpoint="/metrics")

    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(
            SessionMiddleware,
            secret_key=app_instance.config.SECRET_KEY,
            max_age=3600 * 24 * 7,
        )
        logger.info("✅ SessionMiddleware подключён")

    # Rate limit last-added = outermost (runs first). Webhook/health/metrics exempt.
    try:
        from bot.middleware.rate_limit import RateLimitMiddleware

        starlette_app.add_middleware(RateLimitMiddleware, max_calls=120, window_seconds=60)
        logger.info("✅ RateLimitMiddleware подключён")
    except Exception as e:
        logger.warning("⚠️ RateLimitMiddleware не подключён: %s", e)

    _has_admin_secret = bool(
        app_instance.config.ADMIN_PASSWORD or app_instance.config.ADMIN_PASSWORD_HASH
    )
    if _has_admin_secret and app_instance.config.SECRET_KEY:
        try:
            from web_admin.main import app as admin_app

            starlette_app.mount("/admin", admin_app)
            logger.info("✅ Веб-админка смонтирована на /admin")
        except Exception as e:
            logger.error(f"❌ Не удалось смонтировать веб-админку: {e}")
    else:
        logger.warning(
            "⚠️ Веб-админка не смонтирована (нет ADMIN_PASSWORD/ADMIN_PASSWORD_HASH или SECRET_KEY)"
        )

    return starlette_app


async def main_entry():
    app = Application()
    await app.startup()
    starlette_app = create_starlette_app(app)

    config = uvicorn.Config(
        starlette_app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", app.config.PORT or 80)),
        log_level="info",
        lifespan="on",
    )
    server = uvicorn.Server(config)

    loop = asyncio.get_running_loop()

    def _handle_sig(*_):
        logger.info("Signal received, shutting down...")
        asyncio.create_task(app.shutdown())
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_sig)
        except NotImplementedError:
            pass

    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main_entry())
    except KeyboardInterrupt:
        pass
