from unittest.mock import AsyncMock, patch

import pytest

from bot.services.booking import BookingService


@pytest.mark.asyncio
async def test_process_booking_success():
    booking_lines = ["iPhone 15 Pro (ABC123)", "Наличные 500"]
    payments = {'cash': 500.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.booking.extract_serials', side_effect=lambda line: ["ABC123"] if "ABC123" in line else []), \
         patch('bot.services.booking.ItemRepository.get_item_by_text', new=AsyncMock(return_value={'id': 1, 'text': 'iPhone 15 Pro'})), \
         patch('bot.services.booking.ItemRepository.get_item_by_serial', new=AsyncMock(return_value={'id': 1, 'text': 'iPhone 15 Pro'})), \
         patch('bot.services.booking.ItemRepository.mark_item_booked', new=AsyncMock()), \
         patch('bot.services.booking.StatsRepository.add_booking', new=AsyncMock()):

        result = await BookingService.process_booking(booking_lines, payments)

        assert result['success'] is True
        assert len(result['results']) == 1
        assert result['results'][0]['status'] == 'booked'


@pytest.mark.asyncio
async def test_process_booking_no_items():
    booking_lines = ["Просто текст", "Наличные 500"]
    payments = {'cash': 500.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.booking.extract_serials', return_value=[]):
        result = await BookingService.process_booking(booking_lines, payments)
        assert result['success'] is False
        assert result['reason'] == 'no_items'
