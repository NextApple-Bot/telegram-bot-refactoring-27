from unittest.mock import AsyncMock, patch

import pytest

from bot.repositories.stats import StatsRepository


@pytest.mark.asyncio
async def test_add_sale():
    mock_conn = AsyncMock()
    with patch('bot.repositories.stats.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        await StatsRepository.add_sale(item_id=1, count=1, cash=10000)

    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_today_stats():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [
        {'cash': 1000, 'terminal': 200, 'qr': 300, 'transfer': 0, 'invoice': 0, 'installment': 0, 'sales_count': 3},
        {'cash': 500, 'terminal': 100, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0, 'preorders_count': 1},
        {'total': 40000, 'bookings_count': 2},
    ]

    with patch('bot.repositories.stats.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        stats = await StatsRepository.get_today_stats()

    assert stats['sales_count'] == 3
    assert stats['preorders_count'] == 1
    assert stats['bookings_count'] == 2
    assert stats['sales']['cash'] == 1000
    assert stats['preorders']['cash'] == 500
    assert stats['bookings_total'] == 40000
