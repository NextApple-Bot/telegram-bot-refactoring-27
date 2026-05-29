# bot/handlers/__init__.py
from aiogram import Router

# Импортируем только существующие роутеры
from .base import router as base_router
from .commands import router as commands_router
from .callbacks import router as callbacks_router
from .topics import (
    sales_router,
    preorder_router,
    arrival_router,
    assortment_router,
)

# Главный роутер
router = Router()

# Подключаем все роутеры
router.include_router(commands_router)
router.include_router(callbacks_router)
router.include_router(base_router)
router.include_router(sales_router)
router.include_router(preorder_router)
router.include_router(arrival_router)
router.include_router(assortment_router)
