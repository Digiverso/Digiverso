from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service
from app.core.config import load_settings
from app.core.rate_limit import RateLimiter
from app.core.security import VerificationTokenManager
from app.main import app
from app.repository.auth_repository import auth_repository
from app.repository.email_repository import EmailDelivery
from app.services.auth_service import AuthService

PASSWORD = "Abcdef1!"


class FakeEmailGateway:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_verification(
        self,
        correo: str,
        nombre: str,
        verification_url: str,
        expires_at: datetime,
    ) -> EmailDelivery:
        message_id = f"fake_{uuid.uuid4().hex[:12]}"
        self.sent.append(
            {
                "correo": correo,
                "nombre": nombre,
                "url": verification_url,
                "expires_at": expires_at,
                "message_id": message_id,
            }
        )
        return EmailDelivery(
            provider="fake",
            message_id=message_id,
            estado="enviado",
            intento_en=datetime.now(timezone.utc),
        )


def payload_registro(correo: str = "ana@example.com", **cambios: object) -> dict[str, object]:
    datos: dict[str, object] = {
        "nombre": "Ana Pérez",
        "correo": correo,
        "password": PASSWORD,
        "aceptar_politicas": True,
    }
    datos.update(cambios)
    return datos


def extraer_token(gateway: FakeEmailGateway) -> str:
    url = str(gateway.sent[-1]["url"])
    return parse_qs(urlsplit(url).query)["token"][0]


@pytest.fixture
def clock() -> dict[str, datetime]:
    return {"now": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)}


@pytest.fixture
def email_gateway() -> FakeEmailGateway:
    return FakeEmailGateway()


@pytest.fixture
def service(clock: dict[str, datetime], email_gateway: FakeEmailGateway) -> AuthService:
    settings = load_settings()
    return AuthService(
        repo=auth_repository,
        settings=settings,
        email_gateway=email_gateway,
        rate_limiter=RateLimiter(limit=10, window_seconds=600),
        token_manager=VerificationTokenManager(settings.secret_key),
        clock=lambda: clock["now"],
    )


@pytest.fixture
def client(service: AuthService) -> TestClient:
    auth_repository.reset()
    app.dependency_overrides[get_auth_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
