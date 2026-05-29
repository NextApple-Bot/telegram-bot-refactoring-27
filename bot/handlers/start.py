from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from .base import get_main_menu_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
        reply_markup=get_main_menu_keyboard()
    )
