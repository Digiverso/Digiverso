"""Pruebas de aceptación de HU-13 sobre la API HTTP y sus consumidores."""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.catalog_parameters import CatalogParametersService

CATALOG_PARAMETERS_URL = "/api/v1/admin/catalog/parameters"
PRODUCTS_URL = "/api/v1/catalog/products"
CATEGORIES_URL = "/api/v1/catalog/categories"

PRODUCER_HEADERS = {"X-Actor-Id": "usr_productor", "X-Actor-Roles": "productor"}
SCOPE_HEADERS = {
    "X-Actor-Id": "usr_parametros",
    "X-Actor-Roles": "admin.catalog.parameters.write",
}


@pytest.fixture()
def catalog_client(category_settings: Settings) -> Iterator[TestClient]:
    """Cliente sin sobrescribir servicios: ejercita la integración real."""

    application = create_app(category_settings)
    with TestClient(application) as client:
        yield client


def _service(client: TestClient) -> CatalogParametersService:
    return client.app.state.catalog_parameters_service


def _get(client: TestClient, suffix: str = "", headers: dict[str, str] | None = None):
    return client.get(
        f"{CATALOG_PARAMETERS_URL}{suffix}", headers=headers or {}
    )


def _put(
    client: TestClient, payload: dict[str, Any], headers: dict[str, str] | None = None
):
    return client.put(CATALOG_PARAMETERS_URL, json=payload, headers=headers or {})


# Caso 1 --------------------------------------------------------------------
def test_consulta_devuelve_version_vigencia_y_metadatos(
    catalog_client: TestClient,
) -> None:
    response = _get(catalog_client)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Parámetros del catálogo consultados correctamente."
    data = body["data"]
    assert data["version"] == 1
    assert data["vigenteDesde"].endswith(("Z", "+00:00"))
    assert data["modulo"] == "catalogo"
    assert data["parametros"]["CAT-01"] == 3500
    assert data["parametros"]["CAT-10"] == 10
    por_codigo = {item["codigo"]: item for item in data["definiciones"]}
    assert set(por_codigo) == set(data["parametros"])
    assert por_codigo["CAT-01"]["valor"] == 3500
    assert por_codigo["CAT-01"]["tipo"] == "entero"
    assert por_codigo["CAT-01"]["validacion"]["minimo"] == 3500
    assert por_codigo["CAT-05"]["tipo"] == "lista"


# Caso 2 --------------------------------------------------------------------
def test_actualizacion_valida_crea_version_y_auditoria(
    catalog_client: TestClient,
) -> None:
    response = _put(
        catalog_client,
        {"parametros": {"CAT-01": 4000}, "motivo": "Nueva política de precios"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Parámetros del catálogo actualizados."
    assert body["success"] is True
    data = body["data"]
    assert data["version"] == 2
    assert data["parametros"]["CAT-01"] == 4000
    assert data["actualizadoPor"] == "usr_admin"
    assert data["motivo"] == "Nueva política de precios"

    service = _service(catalog_client)
    eventos = service.audit_repository.list_for_entity(
        "catalog:version-2", entidad="parametros_catalogo"
    )
    assert len(eventos) == 1
    assert eventos[0]["accion"] == "parametros_actualizados"
    assert eventos[0]["actorId"] == "usr_admin"
    assert eventos[0]["cambios"]["anteriores"] == {"CAT-01": 3500}
    assert eventos[0]["cambios"]["valores"] == {"CAT-01": 4000}
    assert eventos[0]["cambios"]["versionAnterior"] == 1
    assert service.cache.get(1) is None
    assert service.settings_view.product_min_price == 4000


# Caso 3 --------------------------------------------------------------------
def test_valor_fuera_de_rango_responde_400_y_no_modifica(
    catalog_client: TestClient,
) -> None:
    response = _put(catalog_client, {"parametros": {"CAT-01": 1000}})

    assert response.status_code == 400
    assert response.json()["data"]["codigo"] == "CATALOG_PARAMETER_INVALID"
    assert _get(catalog_client).json()["data"]["version"] == 1
    assert _get(catalog_client).json()["data"]["parametros"]["CAT-01"] == 3500


def test_tipo_invalido_responde_400_y_no_modifica(catalog_client: TestClient) -> None:
    response = _put(catalog_client, {"parametros": {"CAT-01": "4000"}})

    assert response.status_code == 400
    errores = response.json()["data"]["errores"]
    assert errores[0]["motivo"] == "tipo_invalido"
    assert _service(catalog_client).snapshot().value("CAT-01") == 3500


def test_dependencias_incumplidas_responde_400(catalog_client: TestClient) -> None:
    tamano = _put(catalog_client, {"parametros": {"CAT-08": 1024}})
    formatos = _put(catalog_client, {"parametros": {"CAT-05": ["jpg", "mp4"]}})

    assert tamano.status_code == 400
    assert any(
        error["motivo"] == "dependencia"
        for error in tamano.json()["data"]["errores"]
    )
    assert formatos.status_code == 400
    assert _get(catalog_client).json()["data"]["version"] == 1


# Caso 4 --------------------------------------------------------------------
def test_acceso_indebido_devuelve_403(catalog_client: TestClient) -> None:
    assert _get(catalog_client, headers=PRODUCER_HEADERS).status_code == 403
    respuesta = _put(
        catalog_client, {"parametros": {"CAT-01": 4000}}, headers=PRODUCER_HEADERS
    )
    assert respuesta.status_code == 403
    assert respuesta.json()["data"]["codigo"] == "CATALOG_PARAMETERS_FORBIDDEN"


def test_alcance_explicito_autoriza_actualizacion(
    catalog_client: TestClient,
) -> None:
    response = _put(
        catalog_client, {"parametros": {"CAT-10": 8}}, headers=SCOPE_HEADERS
    )

    assert response.status_code == 200
    assert response.json()["data"]["parametros"]["CAT-10"] == 8
    assert response.json()["data"]["actualizadoPor"] == "usr_parametros"


# Caso 5 --------------------------------------------------------------------
def test_historial_conserva_versiones_anteriores(catalog_client: TestClient) -> None:
    _put(catalog_client, {"parametros": {"CAT-01": 4000}})
    _put(catalog_client, {"parametros": {"CAT-10": 8}})

    response = _get(catalog_client, "/history")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["versionActual"] == 3
    assert data["total"] == 3
    assert [item["version"] for item in data["versiones"]] == [3, 2, 1]
    assert data["versiones"][1]["anteriores"] == {"CAT-01": 3500}
    assert data["versiones"][2]["parametros"]["CAT-01"] == 3500
    assert _get(catalog_client, "/history/1").json()["data"]["parametros"]["CAT-10"] == 10
    assert _get(catalog_client, "/history/999").status_code == 404


# Aislamiento ---------------------------------------------------------------
def test_no_acepta_parametros_de_otros_modulos(catalog_client: TestClient) -> None:
    respuesta = _put(catalog_client, {"parametros": {"AUT-01": 10}})

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["moduloPermitido"] == "catalogo"
    assert _get(catalog_client).json()["data"]["version"] == 1


def test_no_acepta_modulo_ajeno(catalog_client: TestClient) -> None:
    respuesta = _put(
        catalog_client, {"modulo": "autenticacion", "parametros": {"CAT-01": 4000}}
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["codigo"] == "CATALOG_PARAMETER_MODULE"


def test_no_acepta_codigo_desconocido(catalog_client: TestClient) -> None:
    respuesta = _put(catalog_client, {"parametros": {"CAT-99": 1}})

    assert respuesta.status_code == 400
    assert respuesta.json()["data"]["modulo"] == "catalogo"


# Consumidores --------------------------------------------------------------
def test_cambio_se_aplica_a_las_funciones_consumidoras(
    catalog_client: TestClient,
) -> None:
    categoria = catalog_client.post(
        CATEGORIES_URL, json={"nombre": "Ilustración"}
    ).json()["data"]["id"]
    payload: dict[str, Any] = {
        "nombre": "Pack de ilustraciones",
        "descripcion": "Ilustraciones digitales en alta resolución.",
        "precio": 3600,
        "categorias": [categoria],
        "medios": [{"tipo": "imagen", "url": "https://cdn.test/uno.webp"}],
    }
    assert catalog_client.post(
        PRODUCTS_URL, json=payload, headers=PRODUCER_HEADERS
    ).status_code == 201

    actualizado = _put(catalog_client, {"parametros": {"CAT-01": 4000}})
    assert actualizado.status_code == 200
    rechazado = catalog_client.post(
        PRODUCTS_URL, json=payload, headers=PRODUCER_HEADERS
    )
    assert rechazado.status_code == 422

    payload["precio"] = 4000
    assert catalog_client.post(
        PRODUCTS_URL, json=payload, headers=PRODUCER_HEADERS
    ).status_code == 201

    assert _put(catalog_client, {"parametros": {"CAT-03": 10}}).status_code == 200
    payload["edadMaxima"] = 12
    assert catalog_client.post(
        PRODUCTS_URL, json=payload, headers=PRODUCER_HEADERS
    ).status_code == 422
