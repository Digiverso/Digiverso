from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

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
