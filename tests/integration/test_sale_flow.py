from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import config


@pytest.mark.asyncio
async def test_sale_flow_success(mock_bot):
    content = """iPhone 15 Pro (ABC123) - 120000₽
Наличные - 120000
Клиент: Иван Иванов
Телефон: +79991234567"""

    message = MagicMock()
    message.message_id = 123
    message.chat = MagicMock(id=config.MAIN_GROUP_ID)
    message.message_thread_id = config.THREAD_SALES
    message.text = content
    message.bot = mock_bot

    with patch.multiple(
        'bot.handlers.topics.sales',
        mark_message_processed=AsyncMock(return_value=True),
        extract_payment_amounts=AsyncMock(return_value={'cash': 120000.0}),
        SaleService=AsyncMock(process_sale=AsyncMock(return_value={
            "sold_items": [(1, "ABC123")], "not_found": [], "is_accessory": False
        })),
        parse_client_data=AsyncMock(return_value={'phones': ['+79991234567'], 'full_name': 'Иван Иванов', 'main_phone': '+79991234567'}),
        ClientRepository=AsyncMock(get_or_create_client=AsyncMock(return_value=1)),
        PaymentService=AsyncMock(add_payments_batch=AsyncMock()),
        safe_react=AsyncMock()
    ):
        from bot.handlers.topics.sales import handle_sales_message
        await handle_sales_message(message)
