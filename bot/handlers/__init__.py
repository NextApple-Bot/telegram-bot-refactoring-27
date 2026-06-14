# bot/handlers/__init__.py

from aiogram import Router

from .commands import router as commands_router
from .callbacks import router as callbacks_router

# Импортируем topics_router целиком (в нём уже подключены все topic-роутеры)
from .topics import topics_router

router = Router()

# Подключаем основные роутеры
router.include_router(commands_router)
router.include_router(callbacks_router)

# Подключаем topics_router (в нём уже есть sales, arrival, preorder, assortment)
router.include_router(topics_router)
