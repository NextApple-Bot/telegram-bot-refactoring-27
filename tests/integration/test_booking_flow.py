from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import config


@pytest.mark.asyncio
async def test_booking_flow_success(mock_bot):
    content = """БРОНЬ:
iPad Pro 11 (IPAD789) - 80000₽
П/О 20000 (нал)
Клиент: Петр Петров
Телефон: +79123456789
Площадка: Авито"""

    message = MagicMock()
    message.message_id = 456
    message.chat = MagicMock(id=config.MAIN_GROUP_ID)
    message.message_thread_id = config.THREAD_PREORDER
    message.text = content
    message.bot = mock_bot

    with patch.multiple(
        'bot.handlers.topics.preorder',
        mark_message_processed=AsyncMock(return_value=True),
        extract_prepayments=AsyncMock(return_value={'cash': 20000.0}),
        parse_client_data=AsyncMock(return_value={'phones': ['+79123456789'], 'full_name': 'Петр Петров', 'main_phone': '+79123456789'}),
        ClientRepository=AsyncMock(get_or_create_client=AsyncMock(return_value=1)),
        BookingService=AsyncMock(process_booking=AsyncMock(return_value={"success": True, "results": [{"status": "booked"}]})),
        send_and_clean=AsyncMock()
    ):
        from bot.handlers.topics.preorder import handle_preorder
        await handle_preorder(message)
