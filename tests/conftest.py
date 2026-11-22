"""Fixtures compartidas de autenticación (HU-01) y categorías (HU-07)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service
from app.cache.category_tree import InMemoryCategoryTreeCache
from app.core.config import Settings, load_settings
from app.core.rate_limit import RateLimiter
from app.core.security import VerificationTokenManager
from app.main import create_app
from app.repository.audit import SQLiteAuditRepository
from app.repository.auth_repository import auth_repository
from app.repository.categories import SQLiteCategoryRepository
from app.repository.database import Database
from app.repository.email_repository import EmailDelivery
from app.services.auth_service import AuthService
from app.services.categories import CategoryService

CATEGORIES_URL = "/api/v1/catalog/categories"
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


# ---------------------------------------------------------------- HU-01
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


# ---------------------------------------------------------------- HU-07
@pytest.fixture()
def category_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="Digiverso API Test",
        app_env="test",
        app_debug=False,
        database_path=tmp_path / "catalog-test.db",
        category_name_min_length=2,
        category_name_max_length=80,
        category_description_max_length=500,
        require_explicit_actor=False,
        default_actor_id="usr_admin",
    )


@pytest.fixture()
def category_service(category_settings: Settings) -> CategoryService:
    database = Database(category_settings.database_path)
    return CategoryService(
        repository=SQLiteCategoryRepository(database),
        audit_repository=SQLiteAuditRepository(database),
        cache=InMemoryCategoryTreeCache(),
        settings=category_settings,
    )


@pytest.fixture()
def create_category(client: TestClient) -> Callable[..., Any]:
    def _create(
        nombre: str,
        *,
        padre_id: str | None = None,
        descripcion: str | None = None,
        orden: int = 0,
        headers: dict[str, str] | None = None,
    ):
        payload: dict[str, Any] = {"nombre": nombre, "orden": orden}
        if padre_id is not None:
            payload["padreId"] = padre_id
        if descripcion is not None:
            payload["descripcion"] = descripcion
        return client.post(CATEGORIES_URL, json=payload, headers=headers or {})

    return _create


# ------------------------------------------------------------- compartido
@pytest.fixture()
def client(
    service: AuthService,
    category_service: CategoryService,
    category_settings: Settings,
) -> TestClient:
    auth_repository.reset()
    test_app = create_app(category_settings)
    test_app.dependency_overrides[get_auth_service] = lambda: service
    with TestClient(test_app) as test_client:
        # El factory crea su propio servicio; usamos el de la fixture para
        # poder inspeccionar repositorio, caché y auditoría desde las pruebas.
        test_client.app.state.category_service = category_service
        yield test_client
    test_app.dependency_overrides.clear()
