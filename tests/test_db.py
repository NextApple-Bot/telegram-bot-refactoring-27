# Basic database tests

import pytest

from sqlalchemy import text
from bot.db import get_async_session

@pytest.mark.asyncio
async def test_db_connection():
    async with get_async_session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1