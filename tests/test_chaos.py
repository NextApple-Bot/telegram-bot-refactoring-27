from unittest.mock import patch

import pytest

from bot.services.cache import cache


@pytest.mark.asyncio
async def test_redis_failure_get():
    with patch.object(cache, 'get', side_effect=ConnectionError), \
         pytest.raises(ConnectionError):
        await cache.get("any_key")


@pytest.mark.asyncio
async def test_redis_failure_set():
    with patch.object(cache, '_redis') as mock_redis, \
         patch.object(cache, '_enabled', True):
        mock_redis.set.side_effect = ConnectionError
        await cache.set("key", "value")   # не должно падать


@pytest.mark.asyncio
async def test_redis_not_configured():
    with patch.object(cache, '_enabled', False):
        result = await cache.get("key")
        assert result is None
        await cache.set("key", "value")
