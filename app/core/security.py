from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Any

import jwt
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.domain.actor import Actor


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
        scopes: tuple[str, ...] = (),
    ) -> str:
        payload = {
            "sub": cuenta_id,
            "rol": rol,
            "scopes": list(scopes),
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


class ActorTokenManager:
    """Token de actor firmado, puente hasta la integración total de HU-01/02/04.

    El productor se obtiene de este token (``sub``) y nunca del cuerpo de la
    petición. Las cabeceras ``X-Actor-Id`` siguen aceptadas para las pruebas y
    para las HU que aún no usan un token de acceso.
    """

    def __init__(self, secret_key: str, ttl_seconds: int = 3600) -> None:
        self._secret_key = secret_key.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def issue(self, actor_id: str, roles: tuple[str, ...] = ()) -> str:
        payload = {
            "sub": actor_id,
            "roles": list(roles),
            "exp": int(time.time()) + self._ttl_seconds,
        }
        body = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        return f"{body}.{self._sign(body)}"

    def parse(self, token: str) -> Actor | None:
        try:
            body, signature = token.split(".", 1)
            if not hmac.compare_digest(signature, self._sign(body)):
                return None
            payload = json.loads(
                base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
            )
            actor_id = payload.get("sub")
            expires = int(payload.get("exp", 0))
            if not isinstance(actor_id, str) or not actor_id or expires <= int(time.time()):
                return None
            roles = payload.get("roles", [])
            return Actor(
                id=actor_id,
                roles=tuple(str(role) for role in roles if isinstance(role, str)),
            )
        except (ValueError, TypeError, KeyError, binascii.Error):
            return None

    def _sign(self, body: str) -> str:
        return hmac.new(self._secret_key, body.encode("ascii"), hashlib.sha256).hexdigest()
