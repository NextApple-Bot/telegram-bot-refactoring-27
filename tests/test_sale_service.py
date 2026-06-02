from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.sale import SaleService


@pytest.mark.asyncio
async def test_process_sale_with_serial():
    content = "iPhone 15 Pro (ABC123) - 1000₽\nНаличные - 1000"
    payments = {'cash': 1000.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    mock_conn = AsyncMock()
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)

    with patch('bot.services.sale.extract_serials', return_value=["ABC123"]), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial', new=AsyncMock(return_value=789)), \
         patch('bot.services.assortment.AssortmentService.remove_by_serial', new=AsyncMock()) as mock_remove, \
         patch('bot.services.sale.StatsRepository.add_sale', new=AsyncMock()), \
         patch('bot.services.sale.get_pool') as mock_get_pool:

        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn_ctx)
        mock_get_pool.return_value = mock_pool

        result = await SaleService.process_sale(content, 123, 456, payments)

        assert result["sold_items"] == [(789, "ABC123")]
        assert result["not_found"] == []
        assert result["is_accessory"] is False
        mock_remove.assert_called_once_with("ABC123", reason='sale', conn=mock_conn)


@pytest.mark.asyncio
async def test_process_sale_without_serial():
    content = "Чехол - 500₽\nНаличные - 500"
    payments = {'cash': 500.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=[]):
        result = await SaleService.process_sale(content, 123, 456, payments)

        assert result["sold_items"] == []
        assert result["is_accessory"] is True
        assert result.get("skip_sale_stats") is True


@pytest.mark.asyncio
async def test_process_sale_not_found():
    content = "iPhone (XYZ999) - 1000₽\nНаличные - 1000"
    payments = {'cash': 1000.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    mock_conn = AsyncMock()
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)

    with patch('bot.services.sale.extract_serials', return_value=["XYZ999"]), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial', new=AsyncMock(return_value=None)), \
         patch('bot.services.sale.get_pool') as mock_get_pool:

        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn_ctx)
        mock_get_pool.return_value = mock_pool

        result = await SaleService.process_sale(content, 123, 456, payments)

        assert result["sold_items"] == []
        assert result["not_found"] == ["XYZ999"]
        assert result.get("skip_sale_stats") is True
        assert result.get("skip_payments") is True
