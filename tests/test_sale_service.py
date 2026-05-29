from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.sale import SaleService


@pytest.fixture
def mock_transaction():
    mock_tx = AsyncMock()
    mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    return mock_tx


@pytest.mark.asyncio
async def test_process_sale_with_serial(mock_transaction):
    content = "iPhone 15 Pro (ABC123) - 1000₽\nНаличные - 1000"
    payments = {'cash': 1000.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0,
                'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=["ABC123"]), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial',
               new=AsyncMock(return_value=789)), \
         patch('bot.services.assortment.AssortmentService.remove_by_serial',
               new=AsyncMock()) as mock_remove, \
         patch('bot.services.sale.StatsRepository.add_sale', new=AsyncMock()), \
         patch('bot.services.sale.get_pool') as mock_get_pool:

        mock_conn = AsyncMock()
        mock_conn.transaction.return_value = mock_transaction
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_ctx
        mock_get_pool.return_value = mock_pool

        result = await SaleService.process_sale(content, 123, 456, payments)

        assert result["sold_items"] == [(789, "ABC123")]
        assert result["not_found"] == []
        mock_remove.assert_called_once_with("ABC123", reason='sale', conn=mock_conn)


@pytest.mark.asyncio
async def test_process_sale_without_serial(mock_transaction):
    content = "Чехол - 500₽\nНаличные - 500"
    payments = {'cash': 500.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0,
                'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=[]):
        result = await SaleService.process_sale(content, 123, 456, payments)

        assert result["sold_items"] == []
        assert result["is_accessory"] is True
        assert result.get("skip_sale_stats") is True


@pytest.mark.asyncio
async def test_process_sale_not_found(mock_transaction):
    content = "iPhone (XYZ999) - 1000₽\nНаличные - 1000"
    payments = {'cash': 1000.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0,
                'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=["XYZ999"]), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial',
               new=AsyncMock(return_value=None)), \
         patch('bot.services.sale.get_pool') as mock_get_pool:

        mock_conn = AsyncMock()
        mock_conn.transaction.return_value = mock_transaction
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_ctx
        mock_get_pool.return_value = mock_pool

        result = await SaleService.process_sale(content, 123, 456, payments)

        assert result["sold_items"] == []
        assert result["not_found"] == ["XYZ999"]
        assert result.get("skip_sale_stats") is True
        assert result.get("skip_payments") is True
