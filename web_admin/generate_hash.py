# Файл: generate_hash.py
"""Вспомогательный скрипт для генерации bcrypt-хэша пароля админки.
Запуск: python generate_hash.py
Вставьте полученный хэш в .env как ADMIN_PASSWORD_HASH.
"""
import getpass

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password = getpass.getpass("Введите пароль для админки: ")
hash_value = pwd_context.hash(password)
print(f"\nADMIN_PASSWORD_HASH={hash_value}")
