# Развёртывание на Render

## Подготовка

1. Убедитесь, что у вас есть аккаунт Render и подключён репозиторий.
2. Настройте сервисы PostgreSQL и Redis (если требуется масштабирование).

## Переменные окружения

Создайте следующие переменные в окружении Render Web Service:

- `BOT_TOKEN` — токен Telegram бота
- `ADMIN_ID` — ID администраторов через запятую
- `MAIN_GROUP_ID` — ID основной группы
- `THREAD_SALES`, `THREAD_ASSORTMENT`, `THREAD_ARRIVAL`, `THREAD_PREORDER` — ID топиков
- `DATABASE_URL` — строка подключения к PostgreSQL
- `REDIS_URL` — строка подключения к Redis (обязательно для масштабирования)
- `RENDER_EXTERNAL_URL` — URL вашего сервиса на Render (например, https://mybot.onrender.com)
- `SECRET_KEY` — секретный ключ для сессий (минимум 32 символа)
- `ADMIN_PASSWORD` или `ADMIN_PASSWORD_HASH` — пароль для входа в админку
- `SCALING_ENABLED` — установите `true` для проверки наличия Redis при запуске

## Деплой

1. Настройте Web Service с типом `web` и стартовой командой `python main.py`.
2. Добавьте Cron Job для ежедневной очистки (см. `render.yaml`).
3. После первого деплоя выполните миграции через SSH: `python manage.py migrate`.

## Zero Downtime

Приложение поддерживает graceful shutdown. Healthcheck эндпоинт `/health` проверяет готовность БД и Redis.

## Масштабирование

Для горизонтального масштабирования:
- Обязательно используйте Redis для хранения FSM.
- Фоновые задачи защищены блокировками Redis, чтобы не дублироваться на разных репликах.
