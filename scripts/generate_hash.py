#!/usr/bin/env python
import getpass

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password = getpass.getpass("Enter admin password: ")
print(f"\nADMIN_PASSWORD_HASH={pwd_context.hash(password)}")
