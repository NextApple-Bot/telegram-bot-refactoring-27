from .topics.sales import router as sales_router
from .topics.preorder import router as preorder_router
from .topics.arrival import router as arrival_router
from .topics.assortment import router as assortment_router

from aiogram import Router

router = Router()
router.include_router(sales_router)
router.include_router(preorder_router)
router.include_router(arrival_router)
router.include_router(assortment_router)
