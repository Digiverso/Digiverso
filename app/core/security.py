from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordHasher:
    def __init__(self) -> None:
        self._hasher = Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


class VerificationTokenManager:
    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key.encode("utf-8")

    def generate(self) -> str:
        return secrets.token_urlsafe(32)

    def hash_token(self, token: str) -> str:
        return hmac.new(self._secret_key, token.encode("utf-8"), hashlib.sha256).hexdigest()
