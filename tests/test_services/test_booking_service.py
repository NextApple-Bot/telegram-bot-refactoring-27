from unittest.mock import AsyncMock, patch

import pytest

from bot.services.booking import BookingService


@pytest.mark.asyncio
async def test_process_booking_success():
    payments = {'cash': 500.0}

    with patch('bot.services.booking.extract_serials', return_value=["ABC123"]), \
         patch('bot.services.booking.ItemRepository.get_item_by_serial',
               new=AsyncMock(return_value={'id': 1})), \
         patch('bot.services.booking.ItemRepository.mark_item_booked', new=AsyncMock()), \
         patch('bot.services.booking.StatsRepository.add_booking', new=AsyncMock()):

        result = await BookingService.process_booking(
            ["iPhone 15 Pro (ABC123)"], payments
        )

        assert result['success'] is True
        assert len(result['results']) == 1


@pytest.mark.asyncio
async def test_process_booking_no_items():
    payments = {'cash': 500.0}

    with patch('bot.services.booking.extract_serials', return_value=[]):
        result = await BookingService.process_booking(["Просто текст"], payments)

        assert result['success'] is False
        assert result['reason'] == 'no_items'
