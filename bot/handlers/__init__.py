# bot/handlers/__init__.py
from aiogram import Router

# Импортируем все роутеры
from .base import router as base_router
from .commands import router as commands_router
from .callbacks import router as callbacks_router
from .service_commands import router as service_commands_router
from .start import router as start_router  # если у вас есть файл start.py (если нет – удалите эту строку)
from .topics import (
    sales_router,
    preorder_router,
    arrival_router,
    assortment_router,
)

# Создаём главный роутер
router = Router()

# Подключаем все роутеры
router.include_router(start_router)          # если есть
router.include_router(commands_router)
router.include_router(callbacks_router)
router.include_router(service_commands_router)
router.include_router(base_router)           # базовые функции
router.include_router(sales_router)
router.include_router(preorder_router)
router.include_router(arrival_router)
router.include_router(assortment_router)
