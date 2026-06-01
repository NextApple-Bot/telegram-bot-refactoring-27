from aiogram import Router

from .base import router as base_router          # общие команды (/start и т.д.)
from .topics import topics_router                # все топики

router = Router()

router.include_router(base_router)
router.include_router(topics_router)
