from aiogram import Router

from .base import router as base_router
from .topics import topics_router

router = Router()

# Подключаем базовые команды
router.include_router(base_router)

# Подключаем все хендлеры по топикам
router.include_router(topics_router)
