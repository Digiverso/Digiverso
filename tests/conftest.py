"""Configuración común de pruebas: base SQLite aislada por test."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

CATEGORIES_URL = "/api/v1/catalog/categories"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="Digiverso API Test",
        app_env="test",
        debug=False,
        database_path=tmp_path / "catalog-test.db",
        category_name_min_length=2,
        category_name_max_length=80,
        category_description_max_length=500,
        require_explicit_actor=False,
        default_actor_id="usr_admin",
    )


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def service(client: TestClient):
    return client.app.state.category_service


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
