from aiogram import Router

from .arrival import router as arrival_router
from .assortment import router as assortment_router
from .preorder import router as preorder_router
from .sales import router as sales_router

# ============================================================
# Родительский роутер для всех топиков группы
# ============================================================
# ВАЖНО: не ставим здесь широкий F.text без thread-фильтра.
# Каждый дочерний роутер сам фильтрует MAIN_GROUP + свой THREAD_*
# через bot.handlers.topics.filters (иначе один хендлер «съедает» событие).

topics_router = Router()

# Порядок не критичен при корректных фильтрах; sales/preorder раньше для ясности
topics_router.include_router(sales_router)
topics_router.include_router(preorder_router)
topics_router.include_router(arrival_router)
topics_router.include_router(assortment_router)

__all__ = ["topics_router"]
