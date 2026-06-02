#!/usr/bin/env python3
"""
Генерация хэша пароля для админ-панели.
Запуск: python web_admin/generate_hash.py
"""
import getpass

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

password = getpass.getpass("Введите пароль администратора: ").strip()

if not password:
    print("Пароль не может быть пустым")
else:
    hashed = pwd_context.hash(password)
    print("\n✅ Добавьте эту строку в .env:\n")
    print(f"ADMIN_PASSWORD_HASH={hashed}\n")
