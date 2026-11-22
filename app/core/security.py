from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Any

import jwt
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings


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


class SessionTokenManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._secret_key = settings.secret_key.encode("utf-8")
        self._private_key, self._public_key = self._resolve_keys(settings)
        public_object = serialization.load_pem_public_key(self._public_key.encode("utf-8"))
        der = public_object.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.key_id = hashlib.sha256(der).hexdigest()[:8]

    @staticmethod
    def _resolve_keys(settings: Settings) -> tuple[str, str]:
        private_key = settings.jwt_private_key.strip()
        public_key = settings.jwt_public_key.strip()
        if private_key:
            if not public_key:
                private_object = serialization.load_pem_private_key(
                    private_key.encode("utf-8"),
                    password=None,
                )
                public_key = private_object.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("utf-8")
            return private_key, public_key

        generated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_key = generated.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("utf-8")
        public_key = generated.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return private_key, public_key

    def generate_refresh_token(self) -> str:
        return f"rt_{secrets.token_urlsafe(32)}"

    def hash_refresh_token(self, token: str) -> str:
        material = f"refresh:{token}".encode("utf-8")
        return hmac.new(self._secret_key, material, hashlib.sha256).hexdigest()

    def issue_access_token(
        self,
        cuenta_id: str,
        rol: str,
        jti: str,
        emitido_en: datetime,
        expira_en: datetime,
    ) -> str:
        payload = {
            "sub": cuenta_id,
            "rol": rol,
            "jti": jti,
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "iat": int(emitido_en.timestamp()),
            "exp": int(expira_en.timestamp()),
        }
        return jwt.encode(
            payload,
            self._private_key,
            algorithm="RS256",
            headers={"kid": self.key_id},
        )

    def decode_access_token(self, token: str, *, verify_exp: bool = True) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            audience=self.settings.jwt_audience,
            issuer=self.settings.jwt_issuer,
            options={
                "require": ["sub", "rol", "jti", "iss", "aud", "iat", "exp"],
                "verify_exp": verify_exp,
            },
        )
