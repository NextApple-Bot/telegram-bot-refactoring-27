# Telegram Bot — Учёт продаж и ассортимента

Production-ready Telegram-бот для управления ассортиментом, бронями и продажами + веб-админка.

## Основные возможности
- Управление ассортиментом через Telegram
- Бронирования и предзаказы
- Статистика продаж
- Web-админка (`/admin`)
- Автоматические миграции, очистка, rate-limit
- Docker + docker-compose

## Быстрый запуск

```bash
cp .env.example .env
# Заполните .env

docker-compose up -d --build
