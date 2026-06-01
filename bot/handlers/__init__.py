from aiogram import Router

from .base import router as base_router
from .topics.arrival import router as arrival_router
from .topics.assortment import router as assortment_router
from .topics.preorder import router as preorder_router
from .topics.sales import router as sales_router

router = Router()

router.include_router(base_router)
router.include_router(arrival_router)
router.include_router(assortment_router)
router.include_router(preorder_router)
router.include_router(sales_router)
