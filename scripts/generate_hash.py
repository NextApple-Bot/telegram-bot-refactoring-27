#!/usr/bin/env python3
"""
Генерация хэша пароля администратора для .env
"""
import getpass
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def main():
    print("Генерация хэша пароля для админ-панели\n")
    password = getpass.getpass("Введите пароль администратора: ").strip()
    
    if not password:
        print("❌ Пароль не может быть пустым")
        return

    hashed = pwd_context.hash(password)
    print("\n✅ Готово! Добавьте эту строку в .env:\n")
    print(f"ADMIN_PASSWORD_HASH={hashed}\n")

if __name__ == "__main__":
    main()
