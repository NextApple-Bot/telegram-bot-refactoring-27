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

    with patch('bot.handlers.topics.sales.mark_message_processed', new=AsyncMock(return_value=True)), \
         patch('bot.handlers.topics.sales.extract_payment_amounts', return_value={'cash': 120000.0, 'terminal': 0, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0}), \
         patch('bot.handlers.topics.sales.SaleService.process_sale', new=AsyncMock(return_value={
             "sold_items": [(1, "ABC123")], "not_found": [], "is_accessory": False, "skip_sale_stats": False, "skip_payments": False
         })), \
         patch('bot.handlers.topics.sales.parse_client_data', return_value={
             'phones': ['+79991234567'], 'full_name': 'Иван Иванов', 'main_phone': '+79991234567',
             'telegram_username': None, 'social_network': None, 'referral_source': None, 'birth_date': None
         }), \
         patch('bot.handlers.topics.sales.ClientRepository.get_or_create_client', new=AsyncMock(return_value=1)), \
         patch('bot.handlers.topics.sales.PaymentService.add_payments_batch', new=AsyncMock()), \
         patch('bot.handlers.topics.sales.safe_react', new=AsyncMock()) as mock_react, \
         patch('bot.handlers.topics.sales.send_and_clean', new=AsyncMock()):

        from bot.handlers.topics.sales import handle_sales_message
        await handle_sales_message(message)

    mock_react.assert_called_once_with(message, '🔥')
