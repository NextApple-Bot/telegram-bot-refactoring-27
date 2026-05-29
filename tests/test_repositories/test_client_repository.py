from unittest.mock import AsyncMock, patch

import pytest

from bot.repositories.client import ClientRepository


@pytest.mark.asyncio
async def test_get_or_create_client_existing():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        'id': 10, 'full_name': 'Старое Имя', 'phones': ''
    }

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        client_id = await ClientRepository.get_or_create_client(
            phone='+79991234567',
            full_name='Новое Имя',
            phones=['+79991234567']
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
            phones=['+79991234567']
        )

    assert client_id == 20
    assert mock_conn.fetchrow.call_count >= 2


@pytest.mark.asyncio
async def test_search_clients():
    mock_rows = [{'id': 1, 'full_name': 'Иван'}, {'id': 2, 'full_name': 'Петр'}]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        result = await ClientRepository.search_clients('Иван')

    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_client_purchases():
    mock_rows = [{'id': 100, 'total_amount': 15000.0}]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        purchases = await ClientRepository.get_client_purchases(1)

    assert len(purchases) == 1
    assert purchases[0]['total_amount'] == 15000.0
