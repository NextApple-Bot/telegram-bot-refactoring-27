from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(scope="function", autouse=True)   # <--- ИСПРАВЛЕНО: session -> function
def set_test_environment(monkeypatch: pytest.MonkeyPatch):
    """Чистая настройка тестового окружения."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/testdb")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("SCALING_ENABLED", "false")
    monkeypatch.setenv("BOT_TOKEN", "test_token")
    monkeypatch.setenv("ADMIN_ID", "123")
    monkeypatch.setenv("MAIN_GROUP_ID", "-100123")
    monkeypatch.setenv("THREAD_SALES", "1")
    monkeypatch.setenv("THREAD_ASSORTMENT", "2")
    monkeypatch.setenv("THREAD_ARRIVAL", "3")
    monkeypatch.setenv("THREAD_PREORDER", "4")
    monkeypatch.setenv("SECRET_KEY", "dummy_secret_key_for_testing_only_min_32_chars")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")


class AsyncSessionMock:
    def __init__(self):
        self.execute = AsyncMock(return_value=MagicMock(
            all=MagicMock(return_value=[]),
            scalar=MagicMock(return_value=None),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
        self.get = AsyncMock(return_value=None)
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
    """Мок healthcheck'ов."""
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
