# bot/handlers/__init__.py

from aiogram import Router

# Топик роутеры (у них есть router)
from .topics.sales import router as sales_router
from .topics.preorder import router as preorder_router
from .topics.arrival import router as arrival_router
from .topics.assortment import router as assortment_router

# Основные роутеры
from .commands import router as commands_router
from .callbacks import router as callbacks_router

router = Router()

# Подключаем роутеры
router.include_router(commands_router)
router.include_router(callbacks_router)

router.include_router(sales_router)
router.include_router(preorder_router)
router.include_router(arrival_router)
router.include_router(assortment_router)
