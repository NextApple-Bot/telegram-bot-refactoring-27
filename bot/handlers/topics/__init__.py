from aiogram import F, Router

from bot import config

from .arrival import router as arrival_router
from .assortment import router as assortment_router
from .preorder import router as preorder_router
from .sales import router as sales_router

# ============================================================
# Родительский роутер для всех топиков группы
# ============================================================

topics_router = Router()

# Общий фильтр: все сообщения должны приходить из основной группы
topics_router.message.filter(F.chat.id == config.MAIN_GROUP_ID)
topics_router.callback_query.filter(F.message.chat.id == config.MAIN_GROUP_ID)

# Подключаем роутеры отдельных топиков
topics_router.include_router(arrival_router)
topics_router.include_router(assortment_router)
topics_router.include_router(preorder_router)
topics_router.include_router(sales_router)


__all__ = ["topics_router"]
