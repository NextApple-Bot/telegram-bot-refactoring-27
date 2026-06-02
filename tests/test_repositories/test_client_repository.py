from unittest.mock import AsyncMock, patch

import pytest

from bot.repositories.client import ClientRepository


@pytest.mark.asyncio
async def test_get_or_create_client_existing_phone():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        'id': 10,
        'full_name': 'Старое Имя',
        'telegram_username': None,
        'social_network': None,
        'referral_source': None,
        'phones': '',
        'birth_date': None,
    }

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        client_id = await ClientRepository.get_or_create_client(
            phone='+79991234567',
            full_name='Новое Имя',
            telegram_username='testuser',
            social_network='VK',
            referral_source='Сайт',
            phones=['+79991234567', '+79991112233'],
            birth_date='01.03.1970'
        )

    assert client_id == 10
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_client_new():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [None, {'id': 20}]

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        client_id = await ClientRepository.get_or_create_client(
            phone='+79991234567',
            full_name='Иван Иванов',
            phones=['+79991234567'],
            birth_date='05.05.1990'
        )

    assert client_id == 20


@pytest.mark.asyncio
async def test_search_clients():
    mock_rows = [
        {'id': 1, 'full_name': 'Иван', 'phone': '+7999', 'telegram_username': 'ivan'},
        {'id': 2, 'full_name': 'Петр', 'phone': '+7888', 'telegram_username': 'petr'},
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        result = await ClientRepository.search_clients('Иван')
    assert len(result) == 2
