from aiogram import Router

from .arrival import router as arrival_router
from .assortment import router as assortment_router
from .preorder import router as preorder_router
from .sales import router as sales_router

# Объединяем все роутеры топиков
topics_router = Router()

topics_router.include_router(arrival_router)
topics_router.include_router(assortment_router)
topics_router.include_router(preorder_router)
topics_router.include_router(sales_router)
