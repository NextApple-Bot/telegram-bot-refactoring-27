import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    import uvloop
    uvloop.install = lambda: None
except ImportError:
    pass

os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"
os.environ["BOT_TOKEN"] = "test_token"
os.environ["ADMIN_ID"] = "123"
os.environ["MAIN_GROUP_ID"] = "-100123"
os.environ["THREAD_SALES"] = "1"
os.environ["THREAD_ASSORTMENT"] = "2"
os.environ["THREAD_ARRIVAL"] = "3"
os.environ["THREAD_PREORDER"] = "4"
os.environ["SECRET_KEY"] = "dummy_secret_key_for_testing_only_min_32_chars"
os.environ["ADMIN_PASSWORD"] = "testpass"


class AsyncSessionMock:
    def __init__(self):
        self.execute = AsyncMock(return_value=MagicMock(all=MagicMock(), scalar=MagicMock(), scalars=MagicMock()))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
        self.get = AsyncMock()
        self.add = MagicMock()
        self.delete = AsyncMock()
        self.begin = MagicMock()
        self.begin_nested = MagicMock()
        self.flush = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class SessionFactoryMock:
    def __call__(self):
        return AsyncSessionMock()


@pytest.fixture(scope="session", autouse=True)
def mock_db_session():
    """Глобальный мок для предотвращения реальных подключений к БД."""
    with patch('bot.db.get_async_session_factory', return_value=SessionFactoryMock()):
        yield


@pytest.fixture(scope="session", autouse=True)
def mock_db_health():
    """Мок healthcheck'ов, чтобы они не обращались к реальным сервисам."""
    with patch('bot.db.check_db_health', new_callable=AsyncMock) as mock_health, \
         patch('bot.db.check_redis_health', new_callable=AsyncMock) as mock_redis:
        mock_health.return_value = True
        mock_redis.return_value = True
        yield


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=AsyncMock(message_id=1))
    bot.send_document = AsyncMock(return_value=AsyncMock(message_id=2))
    bot.delete_message = AsyncMock()
    bot.react = AsyncMock()
    bot.get_me = AsyncMock(return_value=AsyncMock(username="test_bot"))
    bot.delete_webhook = AsyncMock()
    bot.set_webhook = AsyncMock()
    bot.session = AsyncMock()
    bot.session.close = AsyncMock()
    return bot


@pytest.fixture
def mock_state():
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state
