"""Хэширование и проверка паролей (PBKDF2-HMAC-SHA256 с индивидуальной солью)."""
import hashlib
import hmac
import os
from typing import Optional

from .config import PBKDF2_ITERATIONS


def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    """Возвращает пару (соль, хэш) в шестнадцатеричном виде."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Сравнивает хэш введённого пароля с сохранённым за постоянное время."""
    _, digest = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest, hash_hex)
