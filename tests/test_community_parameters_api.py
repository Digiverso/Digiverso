"""Pruebas de aceptación de HU-21 sobre la API HTTP y sus consumidores.

Fixture propia: no modifica ``tests/conftest.py``, compartido con otras HU.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.community_parameters import CommunityParametersService

COMMUNITY_PARAMETERS_URL = "/api/v1/admin/community/parameters"

CONSUMER_HEADERS = {"X-Actor-Id": "usr_consumidor", "X-Actor-Roles": "consumidor"}
SCOPE_HEADERS = {
    "X-Actor-Id": "usr_parametros",
    "X-Actor-Roles": "admin.community.parameters.write",
}


@pytest.fixture()
def community_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        app_name="Digiverso API Test",
        app_env="test",
        app_debug=False,
        database_path=tmp_path / "community-parameters.db",
        require_explicit_actor=False,
        default_actor_id="usr_admin",
        media_storage_dir=tmp_path / "media",
        profile_photo_storage_path=tmp_path / "photos",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        yield client


def _service(client: TestClient) -> CommunityParametersService:
    return client.app.state.community_parameters_service


def _get(client: TestClient, suffix: str = "", headers: dict[str, str] | None = None):
    return client.get(f"{COMMUNITY_PARAMETERS_URL}{suffix}", headers=headers or {})


def _put(
    client: TestClient, payload: dict[str, Any], headers: dict[str, str] | None = None
):
    return client.put(COMMUNITY_PARAMETERS_URL, json=payload, headers=headers or {})


# Caso 1: consulta ---------------------------------------------------------
def test_consulta_devuelve_version_vigencia_y_validaciones(
    community_client: TestClient,
) -> None:
    response = _get(community_client)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Parámetros de comunidad consultados correctamente."
    data = body["data"]
    assert data["version"] == 1
    assert data["vigenteDesde"].endswith(("Z", "+00:00"))
    assert data["modulo"] == "comunidad"
    assert data["parametros"]["COMU-01"] == 1
    assert data["parametros"]["COMU-05"] == 200
    assert data["parametros"]["COMU-11"] is True

    por_codigo = {item["codigo"]: item for item in data["definiciones"]}
    assert set(por_codigo) == set(data["parametros"])
    assert por_codigo["COMU-05"]["valor"] == 200
    assert por_codigo["COMU-05"]["tipo"] == "entero"
    assert por_codigo["COMU-05"]["validacion"]["minimo"] == 1
    assert por_codigo["COMU-03"]["tipo"] == "booleano"
    assert por_codigo["COMU-07"]["dependencias"]


# Caso 2: actualización válida ----------------------------------------------
def test_actualizacion_valida_crea_version_y_auditoria(
    community_client: TestClient,
) -> None:
    response = _put(
        community_client,
        {
            "parametros": {"COMU-02": 1200, "COMU-05": 300},
            "motivo": "Nueva política de convivencia",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Parámetros de comunidad actualizados."
    assert body["success"] is True
    data = body["data"]
    assert data["version"] == 2
    assert data["parametros"]["COMU-02"] == 1200
    assert data["parametros"]["COMU-05"] == 300
    assert data["actualizadoPor"] == "usr_admin"
    assert data["motivo"] == "Nueva política de convivencia"

    service = _service(community_client)
    eventos = service.audit_repository.list_for_entity(
        "community:version-2", entidad="parametros_comunidad"
    )
    assert len(eventos) == 1
    assert eventos[0]["accion"] == "parametros_actualizados"
    assert eventos[0]["actorId"] == "usr_admin"
    assert eventos[0]["cambios"]["anteriores"] == {"COMU-02": 1000, "COMU-05": 200}
    assert eventos[0]["cambios"]["valores"] == {"COMU-02": 1200, "COMU-05": 300}
    assert eventos[0]["cambios"]["versionAnterior"] == 1
    assert service.cache.get(1) is None


def test_cambios_se_aplican_a_las_funciones_consumidoras(
    community_client: TestClient,
) -> None:
    @dataclass(frozen=True)
    class ConsumerSettings:
        community_max_following: int = 200
        community_max_page_size: int = 100
        community_rating_min: int = 1
        community_text_max_length: int = 1000
        community_unique_review: bool = True
        community_require_purchase: bool = True
        max_following: int = 200

    consumer = ConsumerSettings()
    cache = type(
        "FakeCache",
        (),
        {"invalidate": lambda self: setattr(self, "llamadas", self.llamadas + 1),
         "llamadas": 0},
    )()
    service = _service(community_client)
    service.register_consumer(consumer)
    service.register_cache(cache)

    cambios = {
        "COMU-01": 3,
        "COMU-02": 1200,
        "COMU-03": False,
        "COMU-04": False,
        "COMU-05": 280,
    }
    assert _put(community_client, {"parametros": cambios}).status_code == 200

    assert consumer.community_max_following == 280
    assert consumer.max_following == 280
    assert consumer.community_rating_min == 3
    assert consumer.community_text_max_length == 1200
    assert consumer.community_unique_review is False
    assert consumer.community_require_purchase is False
    assert service.settings_view.community_max_following == 280
    assert service.settings_view.max_following == 280
    # Los objetos de configuración de la app también leen la versión vigente.
    assert community_client.app.state.settings.community_max_following == 280
    assert cache.llamadas == 1


# Caso 3: valor inválido ----------------------------------------------------
def test_valor_invalido_responde_400_y_no_modifica(
    community_client: TestClient,
) -> None:
    response = _put(community_client, {"parametros": {"COMU-01": 0}})

    assert response.status_code == 400
    assert response.json()["data"]["codigo"] == "COMMUNITY_PARAMETER_INVALID"
    assert _get(community_client).json()["data"]["version"] == 1
    assert _service(community_client).snapshot().value("COMU-01") == 1


def test_tipo_invalido_responde_400_y_no_modifica(
    community_client: TestClient,
) -> None:
    entero = _put(community_client, {"parametros": {"COMU-05": "300"}})
    booleano = _put(community_client, {"parametros": {"COMU-03": 1}})

    assert entero.status_code == 400
    assert entero.json()["data"]["errores"][0]["motivo"] == "tipo_invalido"
    assert booleano.status_code == 400
    assert _get(community_client).json()["data"]["version"] == 1


def test_dependencia_incumplida_responde_400(community_client: TestClient) -> None:
    response = _put(community_client, {"parametros": {"COMU-07": 10}})

    assert response.status_code == 400
    assert any(
        error["motivo"] == "dependencia"
        for error in response.json()["data"]["errores"]
    )
    assert _get(community_client).json()["data"]["version"] == 1


# Caso 4: acceso indebido ----------------------------------------------------
def test_acceso_indebido_devuelve_403(community_client: TestClient) -> None:
    assert _get(community_client, headers=CONSUMER_HEADERS).status_code == 403
    respuesta = _put(
        community_client,
        {"parametros": {"COMU-05": 300}},
        headers=CONSUMER_HEADERS,
    )
    assert respuesta.status_code == 403
    assert respuesta.json()["data"]["codigo"] == "COMMUNITY_PARAMETERS_FORBIDDEN"


def test_alcance_explicito_autoriza_actualizacion(
    community_client: TestClient,
) -> None:
    response = _put(
        community_client, {"parametros": {"COMU-10": 15}}, headers=SCOPE_HEADERS
    )

    assert response.status_code == 200
    assert response.json()["data"]["parametros"]["COMU-10"] == 15
    assert response.json()["data"]["actualizadoPor"] == "usr_parametros"


# Caso 5: historial ---------------------------------------------------------
def test_historial_conserva_versiones_anteriores(
    community_client: TestClient,
) -> None:
    assert _put(community_client, {"parametros": {"COMU-05": 300}}).status_code == 200
    assert _put(community_client, {"parametros": {"COMU-07": 150}}).status_code == 200

    response = _get(community_client, "/history")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["versionActual"] == 3
    assert data["total"] == 3
    assert [item["version"] for item in data["versiones"]] == [3, 2, 1]
    assert data["versiones"][1]["anteriores"] == {"COMU-05": 200}
    assert data["versiones"][2]["parametros"]["COMU-05"] == 200
    assert _get(community_client, "/history/1").json()["data"]["parametros"]["COMU-05"] == 200
    assert _get(community_client, "/history/999").status_code == 404


# Aislamiento entre módulos -------------------------------------------------
def test_no_acepta_parametros_de_otros_modulos(community_client: TestClient) -> None:
    for codigo in ("AUT-01", "CAT-01", "COM-01"):
        respuesta = _put(community_client, {"parametros": {codigo: 10}})
        assert respuesta.status_code == 400
        assert respuesta.json()["data"]["moduloPermitido"] == "comunidad"
    assert _get(community_client).json()["data"]["version"] == 1


def test_no_acepta_modulo_ajeno_o_codigo_desconocido(
    community_client: TestClient,
) -> None:
    modulo = _put(
        community_client, {"modulo": "catalogo", "parametros": {"COMU-05": 300}}
    )
    desconocido = _put(community_client, {"parametros": {"COMU-99": 1}})

    assert modulo.status_code == 400
    assert modulo.json()["data"]["codigo"] == "COMMUNITY_PARAMETER_MODULE"
    assert desconocido.status_code == 400
    assert desconocido.json()["data"]["modulo"] == "comunidad"
    assert _get(community_client).json()["data"]["version"] == 1


def test_cuerpo_invalido_responde_400(community_client: TestClient) -> None:
    respuesta = _put(community_client, {"parametros": [], "extra": 1})

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["codigo"] == "validacion"
    assert _get(community_client).json()["data"]["version"] == 1
